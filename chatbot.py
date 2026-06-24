from flask import Flask,render_template,request,url_for,redirect,jsonify,Blueprint,session,make_response,flash
import google.generativeai as genai
from db import get_db_connection 
from email_validator import validate_email, EmailNotValidError
from flask_login import login_required,login_user,logout_user,current_user
from werkzeug.security import generate_password_hash,check_password_hash
from flask_jwt_extended import JWTManager,create_access_token,jwt_required,get_jwt_identity
from flask_session import Session
from datetime import timedelta
from flask_socketio import SocketIO,join_room
import uuid


app = Flask(__name__)
auth = Blueprint('auth',__name__)

app.secret_key = "secret123key"
app.permanent_session_lifetime = timedelta(hours=1)

app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = True

Session(app)

socketio = SocketIO(app)

genai.configure(api_key="AQ.Ab8RN6L8XDmbpF1TsvIDQBTXg7NAVkQdMmpS6m-jSyirL1nc8w")

@socketio.on("join_room")
def handle_join(data):
    room = f"{data['user_id']}room"
    join_room(room)

def ai_chatbot_response(user_input):
    model = genai.GenerativeModel("gemini-2.5-flash-lite")  # or "gemini-1.5-pro"
    response = model.generate_content(user_input)
    return response.text

@app.route("/", methods=["GET","POST"])
def chatbot():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        if "name" in request.form:
            name = request.form["name"]
            user_id = name
            room_id = name + "room"
            session['user_id'] = user_id
            session['room_id'] = room_id
            session['name'] = name
            cursor.execute("INSERT INTO chat (name,user_id,room_id) VALUES (%s,%s,%s)", (name,user_id,room_id))
            conn.commit()
            step = 2

        elif "country" in request.form:
            country = request.form["country"]
            cursor.execute("UPDATE chat SET country = %s WHERE id = (SELECT id FROM (SELECT MAX(id) AS id FROM chat) AS t);", (country,))
            conn.commit()
            step = 3

        elif "mobile" in request.form:
            mobile = request.form["mobile"]
            cursor.execute("UPDATE chat SET mobile = %s WHERE id = (SELECT id FROM (SELECT MAX(id) AS id FROM chat) AS t);", (mobile,))
            conn.commit()
            step = 4

        elif "email" in request.form:
            email = request.form["email"]
            cursor.execute("UPDATE chat SET email = %s WHERE id = (SELECT id FROM (SELECT MAX(id) AS id FROM chat) AS t);", (email,))
            conn.commit()
            step = 5

        elif "service" in request.form:
            service = request.form["service"]
            cursor.execute("UPDATE chat SET service = %s WHERE id = (SELECT id FROM (SELECT MAX(id) AS id FROM chat) AS t);", (service,))
            conn.commit()
            step = 6

        else:
            step = 1
    else:
        step = 1

    cursor.close()
    conn.close()
    return render_template("index.html", step=step)



@auth.route("/agent_signup",methods=["POST"])
def agent_signup():
    if request.method == "POST":
        agent_name = str(request.form["agent_name"])
        agent_email = str(request.form["agent_email"])
        agent_password = str(request.form["agent_password"])
        confirm = str(request.form["confirm_password"])
        conn = get_db_connection()
        cursor = conn.cursor()
        if agent_password == confirm:
            cursor.execute("INSERT INTO agents(agent_name,agent_email,agent_password) VALUES (%s,%s,%s)",(agent_name,agent_email,agent_password))
            conn.commit()
            cursor.close()
            conn.close()
            return render_template("login.html")
        else:
            return render_template("signup.html",conf = "password did not match")
    return render_template("login.html")



@auth.route("/agent_login",methods=["POST"])
def agent_login():
    if request.method == "POST":
        agent_login_name = str(request.form["Lagent_name"])
        agent_login_password = str(request.form["Lagent_password"])
        session["agent_id"] = agent_login_name
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT agent_name,agent_password from agents where agent_name=%s AND agent_password=%s",(agent_login_name,agent_login_password))
        checkp = cursor.fetchone()
        cursor.close()
        conn.close()
        if checkp:
            return render_template("agent.html")
        return render_template("login.html",msg = "invalid login")   
    return render_template("agent.html") 
        

app.register_blueprint(auth)

@app.route("/chats",methods=["GET"])
def chats():
    socketio.emit('USERS',{})
    return render_template("chats.html",user_id = session['user_id'])

@app.route("/agent_chat",methods=["GET"])
def agent_chat():
    user_id = request.args.get("user_id")
    session['room_id'] = f"{user_id}room"
    return render_template("agent_chatbot.html",user_id = user_id,room_id = session['room_id'])

@socketio.on('agent_res')
def agent_res(resp):
    agent_message = resp["response"]
    user_id = resp['user_id']
    room = resp['room_id']
    role2 = "agent"
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chatbot_chats (role,message,user_id,room_id) VALUES(%s,%s,%s,%s)",(role2,agent_message,user_id,room))
    conn.commit()
    cursor.execute("SELECT message FROM chatbot_chats WHERE role = 'user' ORDER BY id DESC LIMIT 1")
    ress = cursor.fetchall()
    cursor.close()
    conn.close()
    socketio.emit("new_message",{"role":role2,"message":agent_message},room=room)
    
@socketio.on('user_response')
def user_response(data):
    user_input = data["message"]
    user_id = session.get('user_id')
    room = session.get('room_id')
    role = "user"
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chatbot_chats (role,message,user_id,room_id) VALUES(%s,%s,%s,%s)",(role,user_input,user_id,room))
    conn.commit()
    cursor.execute("SELECT message FROM chatbot_chats WHERE role = 'agent' ORDER BY id DESC LIMIT 1")
    mess2 = cursor.fetchall()
    cursor.close()
    conn.close()
    socketio.emit("new_message",{"role":role,"message":user_input},room=room)

@socketio.on('USERS')
def user_info(data):
    # Yeh values login ke time set karni hongi
    user_id = session.get('user_id')
    room_id = session.get('room_id')
    users = []
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id,name,country,mobile,email,service FROM chat ORDER BY id DESC;")
    user_information = cursor.fetchall()
    cursor.close()
    conn.close()

    if user_information:
        for user in user_information:
            users.append({
                "user_id": user_id if user_id else user[0],   # agar session empty hai to DB id use karo
                "name": user[1],
                "email": user[4],
                "service": user[5],
                "room_id": room_id if room_id else "N/A"
            })  
    socketio.emit("all_users",users)  # broadcast zaruri hai


    

@app.route("/login_page",methods=["GET"])
def login_page():
    return render_template("login.html")

@app.route("/signup_page",methods=["GET"])
def signup_page():
    return render_template("signup.html")

if __name__ == "__main__":
    socketio.run(app,debug=True)