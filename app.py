import json
import os
import secrets
import smtplib
from datetime import datetime
from functools import wraps

# ---------------- APP SETUP ----------------
from flask import Flask
from flask import jsonify
from flask import render_template, session
from pymongo import MongoClient

app = Flask(__name__)
app.secret_key = "super_secret_key_12345"
app.config["SESSION_PERMANENT"] = False

# ---------------- DATABASE ----------------
# Connect to MongoDB
client = MongoClient("mongodb://localhost:27017/")  # Local MongoDB
db = client["voting_system"]
notices_collection = db["notices"]
# Collections
users_collection = db["users"]
votes_collection = db["votes"]
blockchain_collection = db["blockchain"]
admin_collection = db["admin"]
applications_collection = db["applications"]  # For voter registration
notice_collection = db["notice"]   # NEW

# ---------------- FILE UPLOAD CONFIG ----------------
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------- HELPER FUNCTIONS ----------------

def allowed_file(filename):
    """
    Check if uploaded file has an allowed extension
    """
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ---------------- LOGIN REQUIRED ----------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


# ---------------- LAMPORT SIGNATURE ----------------
def generate_lamport_keys():
    private_key = [secrets.token_bytes(32) for _ in range(512)]
    public_key = [hashlib.sha256(k).hexdigest() for k in private_key]
    return private_key, public_key


# ---------------- HASH FUNCTION ----------------
def hash_block(block_data):

    # copy block so original is not modified
    block_copy = block_data.copy()

    # remove MongoDB id if exists
    block_copy.pop("_id", None)

    return hashlib.sha256(
        json.dumps(block_copy, sort_keys=True).encode()
    ).hexdigest()


# ---------------- CREATE BLOCK ----------------
def create_block(voter_hash, candidate):

    last_block = blockchain_collection.find_one(sort=[("index", -1)])

    prev_hash = last_block["hash"] if last_block else "0"
    index = last_block["index"] + 1 if last_block else 1

    block = {
        "index": index,
        "time": str(datetime.datetime.now()),
        "voter_hash": voter_hash,
        "candidate": candidate,
        "previous_hash": prev_hash
    }

    block["hash"] = hash_block(block)

    return block


# ---------------- BLOCKCHAIN VALIDATION ----------------
def is_chain_valid():

    blockchain = list(blockchain_collection.find().sort("index", 1))

    for i in range(1, len(blockchain)):

        prev_block = blockchain[i - 1]
        current_block = blockchain[i]

        # Check previous hash link
        if current_block["previous_hash"] != prev_block["hash"]:
            return False

        # Copy block
        block_copy = current_block.copy()

        # Remove fields not used in hashing
        block_copy.pop("_id", None)
        stored_hash = block_copy.pop("hash")

        # Recalculate hash
        recalculated_hash = hash_block(block_copy)

        if stored_hash != recalculated_hash:
            return False

    return True


# ================= ROUTES =================

@app.route("/")
def home():
    return render_template("home.html", user=session.get("user"))




# ---------- LOGIN ----------
@app.route("/login", methods=["GET","POST"])
def login():

    users = list(users_collection.find())

    if request.method == "POST":

        name = request.form.get("full_name").strip()
        voter_id = request.form.get("voter_id").strip()
        gender = request.form.get("gender")
        ward = request.form.get("ward")

        user = users_collection.find_one({
            "full_name": name,
            "voter_id": voter_id,
            "gender": gender,
            "$or": [
                {"ward": ward},
                {"ward": int(ward)}
            ]
        })

        if user:
            # ✅ BASIC SESSION
            session["user"] = user["full_name"]
            session["voter_id"] = user["voter_id"]
            session["gender"] = user["gender"]
            session["ward"] = user["ward"]

            # ✅ EXTRA DATA
            session["dob"] = user.get("dob")
            session["mobile"] = user.get("mobile")
            session["email"] = user.get("email")
            session["address"] = user.get("address")
            session["city"] = user.get("city")
            session["pincode"] = user.get("pincode")

            # 🔥 NEW (IMPORTANT)
            session["disability"] = user.get("disability", "No")

            flash("Login Successful")
            return redirect(url_for("home"))

        else:
            flash("Invalid Details")

    return render_template("user/login.html", users=users)



import os, bcrypt
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {"png","jpg","jpeg","pdf"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".",1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/apply_card", methods=["GET","POST"])
def apply_card():

    if request.method == "POST":

        full_name = request.form.get("full_name")
        dob = request.form.get("dob")
        gender = request.form.get("gender")

        # ✅ NEW FIELD
        disability = request.form.get("disability")

        mobile = request.form.get("mobile")
        email = request.form.get("email").lower()
        address = request.form.get("address")
        city = request.form.get("city")
        pincode = request.form.get("pincode")
        ward = request.form.get("ward")

        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        # Password validation
        if password != confirm_password:
            flash("Passwords do not match")
            return redirect(request.url)

        # Duplicate email check
        existing = applications_collection.find_one({"email": email})
        if existing:
            flash("Application already submitted with this email")
            return redirect(request.url)

        # Hash password
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        # File upload
        id_proof_file = request.files.get("id_proof")

        if not id_proof_file or id_proof_file.filename == "":
            flash("Identity proof required")
            return redirect(request.url)

        if not allowed_file(id_proof_file.filename):
            flash("Invalid file format")
            return redirect(request.url)

        # Generate unique ID
        user_hash = hashlib.sha256(email.encode()).hexdigest()[:10]

        filename = secure_filename(id_proof_file.filename)
        id_filename = f"{user_hash}_{filename}"

        filepath = os.path.join(app.config["UPLOAD_FOLDER"], id_filename)
        id_proof_file.save(filepath)

        # ✅ INSERT INTO DATABASE
        applications_collection.insert_one({

            "user_hash": user_hash,
            "full_name": full_name,
            "dob": dob,
            "gender": gender,
            "disability": disability,   # ✅ SAVED
            "mobile": mobile,
            "email": email,
            "address": address,
            "city": city,
            "pincode": pincode,
            "ward": ward,
            "id_proof": id_filename,
            "password": hashed_password,
            "status": "Pending",
            "voter_id": None,
            "created_at": datetime.datetime.utcnow()

        })

        flash("Application submitted successfully")
        return redirect(url_for("application_status"))

    return render_template("apply_card.html")



@app.route("/application_status", methods=["GET","POST"])
def application_status():

    app_data = None

    if request.method == "POST":

        email = request.form.get("email").lower()
        password = request.form.get("password")

        user = applications_collection.find_one({"email": email})

        if not user:
            flash("Application not found")
            return render_template("application_status.html", app_data=None)

        stored_password = user.get("password")

        if not stored_password:
            flash("Password missing in database")
            return render_template("application_status.html", app_data=None)

        # Convert to bytes if stored as string
        if isinstance(stored_password, str):
            stored_password = stored_password.encode()

        # Check if hash is valid bcrypt
        if not stored_password.startswith(b"$2"):
            flash("Password format error in database")
            return render_template("application_status.html", app_data=None)

        try:
            if bcrypt.checkpw(password.encode(), stored_password):
                app_data = user
            else:
                flash("Invalid password")
        except ValueError:
            flash("Invalid password format in database")

    return render_template("application_status.html", app_data=app_data)






# YOUR GMAIL DETAILS
EMAIL_ADDRESS = "unnatinannavare70@gmail.com"
EMAIL_APP_PASSWORD = "xlsn dnyj tcol ohzx"

def send_email_otp(receiver_email, otp):

    subject = "Admin Login OTP - Voting System"
    body = f"""
Hello Admin,

Your OTP for Admin Login is:

{otp}

Do not share this OTP with anyone.

Voting System Security
"""

    message = f"Subject: {subject}\n\n{body}"

    try:

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()

        server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)

        server.sendmail(EMAIL_ADDRESS, receiver_email, message)

        server.quit()

        print("✅ OTP Email Sent Successfully")

    except Exception as e:
        print("❌ Email Error:", e)


@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        email = request.form["email"]
        phone = request.form["phone"]
        password = request.form["password"]

        # Find admin by email & password
        admin = admin_collection.find_one({
            "email": email,
            "password": password
        })

        # ✅ FIXED CONDITION (compare phone from DB)
        if admin and admin["phone"] == phone:

            otp = str(random.randint(100000, 999999))

            session["admin_otp"] = otp
            session["admin_email"] = email

            # Send OTP
            send_email_otp(email, otp)

            print("Generated OTP:", otp)

            return redirect(url_for("verify_admin_otp"))

        else:
            flash("Invalid Admin Credentials")

    return render_template("admin/admin_login.html")




@app.route("/verify_admin_otp", methods=["GET","POST"])
def verify_admin_otp():

    if request.method == "POST":

        entered_otp = request.form["otp"]
        real_otp = session.get("admin_otp")

        if entered_otp == real_otp:

            session["admin_logged_in"] = True

            flash("Login Successful")

            return redirect(url_for("admin_dashboard"))

        else:
            flash("Invalid OTP")

    return render_template("admin/verify_otp.html")




@app.route("/admin_dashboard")
def admin_dashboard():

    users = db.users
    votes = db.votes
    candidates = db.applications

    # totals
    total_voters = users.count_documents({})
    total_votes = votes.count_documents({})
    total_candidates = candidates.count_documents({})

    # gender stats
    male_voters = users.count_documents({"gender": "Male"})
    female_voters = users.count_documents({"gender": "Female"})
    other_voters = users.count_documents({"gender": "Other"})

    # ✅ disability check
    disability_exists = users.count_documents({"disability": {"$exists": True}}) > 0

    if disability_exists:
        disabled_voters = users.count_documents({"disability": "Yes"})

        # ✅ NON-DISABLED USERS
        non_disabled_voters = users.count_documents({
            "$or": [
                {"disability": "No"},
                {"disability": {"$exists": False}}
            ]
        })
    else:
        disabled_voters = None
        non_disabled_voters = None

    # aggregation
    pipeline = [
        {
            "$lookup": {
                "from": "users",
                "localField": "voter",
                "foreignField": "voter_hash",
                "as": "user_info"
            }
        },
        {"$unwind": "$user_info"},

        {
            "$group": {
                "_id": "$candidate",
                "total_votes": {"$sum": 1},

                "male_votes": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$user_info.gender", "Male"]}, 1, 0
                        ]
                    }
                },

                "female_votes": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$user_info.gender", "Female"]}, 1, 0
                        ]
                    }
                },

                "other_votes": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$user_info.gender", "Other"]}, 1, 0
                        ]
                    }
                },

                "disabled_votes": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$user_info.disability", "Yes"]}, 1, 0
                        ]
                    }
                }

            }
        },

        {"$sort": {"total_votes": -1}}
    ]

    results = list(votes.aggregate(pipeline))
    winner = results[0]["_id"] if results else "No Votes"

    return render_template(
        "admin/admin_dashboard.html",
        total_voters=total_voters,
        total_votes=total_votes,
        total_candidates=total_candidates,
        male_voters=male_voters,
        female_voters=female_voters,
        other_voters=other_voters,
        disabled_voters=disabled_voters,
        non_disabled_voters=non_disabled_voters,  # ✅ IMPORTANT
        results=results,
        winner=winner
    )


# ---------- VOTE ----------
import hashlib


@app.route("/vote", methods=["GET", "POST"])
@login_required
def vote():

    voter_id = session["voter_id"]
    gender = session["gender"]
    ward = session["ward"]

    # 🔥 NEW
    disability = session.get("disability", "No")

    # 🔐 Hash voter_id
    voter_hash = hashlib.sha256(voter_id.encode()).hexdigest()

    # 🚫 Already voted check
    if votes_collection.find_one({"voter": voter_hash}):
        return render_template("user/already_vote.html", user=session["user"])

    if request.method == "POST":

        candidate = request.form["candidate"]

        # ✅ SAVE EVERYTHING (UPDATED)
        votes_collection.insert_one({
            "voter": voter_hash,
            "candidate": candidate,
            "gender": gender,
            "ward": ward,
            "disability": disability,   # 🔥 ADDED
            "date": time.strftime("%Y-%m-%d")
        })

        # ⛓ Blockchain (unchanged)
        block = create_block(voter_hash, candidate)
        blockchain_collection.insert_one(block)

        return render_template(
            "user/vote_successfull.html",
            user=session["user"],
            candidate=candidate
        )

    return render_template("user/vote.html")




@app.route("/vote_successful")
@login_required
def vote_successful():

    user = session.get("user")
    candidate = session.get("candidate")

    return render_template(
        "user/vote_successfull.html",
        user=user,
        candidate=candidate
    )


@app.route("/profile")
def profile():
    if "user" not in session:
        flash("Please login first")
        return redirect(url_for("login"))

    user = users_collection.find_one({
        "full_name": session["user"],
        "voter_id": session["voter_id"]
    })

    if not user:
        flash("User not found")
        return redirect(url_for("login"))

    user_data = {
        "full_name": user.get("full_name", ""),
        "voter_id": user.get("voter_id", ""),
        "gender": user.get("gender", ""),
        "disability": user.get("disability", "No"),  # ✅ IMPORTANT
        "ward": user.get("ward", ""),
        "dob": user.get("dob", ""),
        "mobile": user.get("mobile", ""),
        "email": user.get("email", ""),
        "address": user.get("address", ""),
        "city": user.get("city", ""),
        "pincode": user.get("pincode", "")
    }

    return render_template("user/profile.html", user=user_data)


@app.route("/help")
def help():
    return render_template("user/help.html")


# ---------- ADMIN NOTICE PAGE ----------
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.route("/admin_notice")
def admin_notice():
    return render_template("admin/admin_notice.html")


@app.route("/upload_notice", methods=["POST"])
def upload_notice():
    title = request.form.get("title")
    description = request.form.get("description")
    file = request.files.get("image")

    filename = None

    if file and file.filename != "":
        filename = secure_filename(file.filename)
        filename = str(int(datetime.datetime.now().timestamp())) + "-" + filename
        file.save(os.path.join("static/uploads", filename))

    notice = {
        "title": title,
        "description": description,
        "image": filename,
        "createdAt": datetime.datetime.now().strftime("%Y-%m-%d")
    }

    notice_collection.insert_one(notice)

    return redirect(url_for("admin_notice"))


@app.route("/notices")
def notices():
    all_notices = list(notice_collection.find().sort("createdAt", -1))
    return render_template("public/notices.html", notices=all_notices)



# API TO FETCH NOTICES
@app.route("/notice")
def notice():
    return render_template("notice.html")


@app.route("/get_notices")
def get_notices():

    notices = []

    for n in notice_collection.find().sort("createdAt", -1):

        n["_id"] = str(n["_id"])

        if n.get("image"):
            n["image"] = "/static/uploads/" + n["image"]

        notices.append(n)

    return jsonify(notices)






@app.route("/admin_voters")
def admin_voters():
    parties = ["BJP","Congress","AAP","Shiv Sena","BSP","CPI","NCP","TMC"]
    wards = [str(i) for i in range(1,11)]

    stats = {
        party: {
            "total": 0,
            "male": 0,
            "female": 0,
            "other": 0,
            "disabled": 0,
            "non_disabled": 0,   # ✅ NEW
            "wards": {ward: 0 for ward in wards}
        } for party in parties
    }

    votes = list(votes_collection.find())

    for v in votes:
        party = v.get("candidate")
        ward = str(v.get("ward"))
        gender = v.get("gender")
        disability = v.get("disability", "No")

        if party in stats:
            stats[party]["total"] += 1

            # gender
            if gender == "Male":
                stats[party]["male"] += 1
            elif gender == "Female":
                stats[party]["female"] += 1
            elif gender == "Other":
                stats[party]["other"] += 1

            # ✅ disability logic
            if disability == "Yes":
                stats[party]["disabled"] += 1
            else:
                stats[party]["non_disabled"] += 1  # ✅ NEW

            if ward in stats[party]["wards"]:
                stats[party]["wards"][ward] += 1

    party_colors = {
        "BJP": "#bfa76a",
        "Congress": "#1f4d3f",
        "AAP": "#256d3b",
        "Shiv Sena": "#7b3e00",
        "BSP": "#d4af37",
        "CPI": "#0f5132",
        "NCP": "#4b5320",
        "TMC": "#3b7a57"
    }

    import time
    report_time = time.strftime("%d %B %Y, %H:%M:%S")

    return render_template(
        "admin/admin_voters.html",
        stats=stats,
        wards=wards,
        parties=parties,
        party_colors=party_colors,
        report_time=report_time
    )



@app.route("/applications")
def applications():

    applications = list(db.applications.find())

    return render_template(
        "admin/applications.html",
        applications=applications
    )



@app.route("/full_application/<id>")
def full_application(id):

    application = db.applications.find_one({"_id": ObjectId(id)})

    return render_template(
        "admin/full_application.html",
        application=application
    )


import random


from flask import request, redirect, url_for, flash
from bson.objectid import ObjectId

from flask_mail import Mail, Message


EMAIL_ADDRESS = "unnatinannavare70@gmail.com"
EMAIL_APP_PASSWORD = "xlsn dnyj tcol ohzx"

app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = EMAIL_ADDRESS
app.config["MAIL_PASSWORD"] = EMAIL_APP_PASSWORD

mail = Mail(app)



def send_voter_id_email(user_email, name, voter_id):
    try:
        print("📨 Sending email to:", user_email)

        msg = Message(
            subject="Voter ID Approved - Nagarpalika Election 2026",
            sender=EMAIL_ADDRESS,
            recipients=[user_email]
        )

        msg.body = f"""
Dear {name},

Your voter registration has been successfully approved.

━━━━━━━━━━━━━━━━━━━━━━
Voter ID: {voter_id}
━━━━━━━━━━━━━━━━━━━━━━

You are now eligible to vote.

Regards,
Election Commission
"""

        mail.send(msg)
        print("✅ Email Sent Successfully")

    except Exception as e:
        print("❌ EMAIL ERROR:", e)


def send_rejection_email(user_email, name):
    try:
        print("📨 Sending rejection email to:", user_email)

        msg = Message(
            subject="Application Rejected - Nagarpalika Election 2026",
            sender=EMAIL_ADDRESS,
            recipients=[user_email]
        )

        msg.body = f"""
Dear {name},

Your application has been rejected.

Please reapply with correct details.

Regards,
Election Commission
"""

        mail.send(msg)
        print("✅ Rejection Email Sent")

    except Exception as e:
        print("❌ EMAIL ERROR:", e)




@app.route("/approve_application/<id>", methods=["POST"])
def approve_application(id):

    voter_id = request.form.get("voter_id")

    # 🔴 Check duplicate voter ID
    if db.users.find_one({"voter_id": voter_id}):
        flash("⚠️ Voter ID already exists")
        return redirect(url_for("full_application", id=id))

    # 🔍 Get application
    application = db.applications.find_one({"_id": ObjectId(id)})
    if not application:
        flash("❌ Application not found")
        return redirect(url_for("applications"))

    print("EMAIL FOUND:", application.get("email"))

    # ✅ Update application
    db.applications.update_one(
        {"_id": ObjectId(id)},
        {"$set": {"status": "Approved", "voter_id": voter_id}}
    )

    # ✅ Copy to users collection
    user_data = application.copy()
    user_data.pop("_id", None)

    user_data["voter_id"] = voter_id
    user_data["status"] = "Approved"

    db.users.insert_one(user_data)

    # ✅ Send Email
    send_voter_id_email(
        application.get("email"),
        application.get("full_name"),
        voter_id
    )

    flash("✅ Approved & Email Sent")
    return redirect(url_for("applications"))



#✅ 4. REJECT ROUTE (Fixed)
@app.route("/reject_application/<id>", methods=["POST"])
def reject_application(id):

    application = db.applications.find_one({"_id": ObjectId(id)})
    if not application:
        flash("❌ Application not found")
        return redirect(url_for("applications"))

    db.applications.update_one(
        {"_id": ObjectId(id)},
        {"$set": {"status": "Rejected"}}
    )

    send_rejection_email(
        application.get("email"),
        application.get("full_name")
    )

    flash("❌ Rejected & Email Sent")
    return redirect(url_for("applications"))








# ---------- RESULT ----------
import time


@app.route("/admin_result")
def admin_result():

    pipeline = [
        {"$group": {"_id": "$candidate", "votes": {"$sum": 1}}},
        {"$sort": {"votes": -1}}
    ]

    data = list(votes_collection.aggregate(pipeline))
    results = {item["_id"]: item["votes"] for item in data}

    winner = None
    tie = False

    if results:
        max_votes = max(results.values())
        winners = [k for k, v in results.items() if v == max_votes]

        if len(winners) > 1:
            tie = True
        else:
            winner = winners[0]

    report_time = time.strftime("%d %B %Y, %I:%M %p")

    return render_template(
        "admin/admin_result.html",
        results=results,
        winner=winner,
        tie=tie,
        report_time=report_time
    )




# ---------- BLOCKCHAIN VIEW ----------
@app.route("/blocks")
@login_required
def blocks():

    blockchain = list(blockchain_collection.find({}, {"_id": 0}).sort("index", 1))

    return render_template("blocks.html", blockchain=blockchain)


# ---------- LOGOUT ----------
@app.route("/logout")
@login_required
def logout():

    session.clear()
    return redirect(url_for("home"))


# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)


