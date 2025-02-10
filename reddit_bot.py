import praw
import openai
import time
import logging
import schedule
import threading
from flask import Flask, render_template, request, redirect, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Flask App Setup & Databse configuration
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///bot_data.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "supersecretkey"
db = SQLAlchemy(app)

# Reddit API Credentials (Replace with your details)
REDDIT_CLIENT_ID = "UwareKinetikbot"
REDDIT_CLIENT_SECRET = "mejUk9-ziDaPUSQrnvgO1LtdWpSSqg"
REDDIT_USERNAME = "Important_Dare4361"
REDDIT_PASSWORD = "uware2006"
REDDIT_USER_AGENT = "UwareKinetikbot v1.0"

# OpenAI API Key
OPENAI_API_KEY = "your_openai_api_key"

# Flask Login Setup (User Authentication)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# Database Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(300), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Keyword(db.Model): #stores keywords on bot reddit
    id = db.Column(db.Integer, primary_key=True)
    keyword = db.Column(db.String(100), unique=True, nullable=False)

class Subreddit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

class Log(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_title = db.Column(db.String(300), nullable=False)
    post_url = db.Column(db.String(300), nullable=False)
    timestamp = db.Column(db.DateTime, default=time.strftime("%Y-%m-%d %H:%M:%S"))

# Authentication Loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Authenticate with Reddit API
def authenticate():
    return praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        username=REDDIT_USERNAME,
        password=REDDIT_PASSWORD,
        user_agent=REDDIT_USER_AGENT,
    )

# AI Response Generator
def generate_ai_response(post_title):
    prompt = f"Reddit user asked: {post_title}. Provide a helpful and concise answer."
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    return response["choices"][0]["message"]["content"]

# Monitor Subreddits
def monitor_subreddit():
    reddit = authenticate()
    subreddits = [s.name for s in Subreddit.query.all()]
    keywords = [k.keyword for k in Keyword.query.all()]

    for sub_name in subreddits:
        subreddit = reddit.subreddit(sub_name)
        for submission in subreddit.new(limit=10):
            title = submission.title.lower()
            if any(keyword in title for keyword in keywords) and not submission.saved:
                try:
                    ai_reply = generate_ai_response(title)
                    submission.reply(ai_reply)
                    submission.save()

                    log_entry = Log(post_title=submission.title, post_url=submission.url)
                    db.session.add(log_entry)
                    db.session.commit()

                    logging.info(f"Replied to post in {sub_name}: {submission.title}")

                except praw.exceptions.APIException as e:
                    logging.error(f"Reddit API error: {e}")
                except Exception as e:
                    logging.error(f"Unexpected error: {e}")

# Flask Routes
@app.route("/")
@login_required
def index():
    keywords = Keyword.query.all()
    subreddits = Subreddit.query.all()
    logs = Log.query.order_by(Log.timestamp.desc()).limit(10).all()
    return render_template("index.html", keywords=keywords, subreddits=subreddits, logs=logs)

@app.route("/add_keyword", methods=["POST"])
@login_required
def add_keyword():
    keyword = request.form["keyword"].strip().lower()
    if keyword and not Keyword.query.filter_by(keyword=keyword).first():
        db.session.add(Keyword(keyword=keyword))
        db.session.commit()
    return redirect("/")

@app.route("/delete_keyword/<int:id>")
@login_required
def delete_keyword(id):
    keyword = Keyword.query.get_or_404(id)
    db.session.delete(keyword)
    db.session.commit()
    return redirect("/")

@app.route("/add_subreddit", methods=["POST"])
@login_required
def add_subreddit():
    sub_name = request.form["subreddit"].strip().lower()
    if sub_name and not Subreddit.query.filter_by(name=sub_name).first():
        db.session.add(Subreddit(name=sub_name))
        db.session.commit()
    return redirect("/")

@app.route("/delete_subreddit/<int:id>")
@login_required
def delete_subreddit(id):
    subreddit = Subreddit.query.get_or_404(id)
    db.session.delete(subreddit)
    db.session.commit()
    return redirect("/")

@app.route("/run-bot")
@login_required
def run_bot():
    threading.Thread(target=monitor_subreddit).start()
    return redirect("/")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect("/")
        flash("Invalid login credentials!", "danger")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")

# Run Flask App
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    schedule.every(10).minutes.do(monitor_subreddit)
    threading.Thread(target=lambda: [schedule.run_pending(), time.sleep(60)], daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
