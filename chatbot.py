from flask import Flask,render_template,request,url_for,redirect,jsonify,Blueprint,session,make_response,flash,send_from_directory
import google.generativeai as genai
from db import get_db_connection 
from email_validator import validate_email, EmailNotValidError
from flask_login import login_required,login_user,logout_user,current_user
from werkzeug.security import generate_password_hash,check_password_hash
from flask_jwt_extended import JWTManager,create_access_token,jwt_required,get_jwt_identity
from flask_session import Session
from datetime import timedelta
from flask_socketio import SocketIO,join_room,leave_room,send,emit
import uuid
import os


app = Flask(__name__)
auth = Blueprint('auth',__name__)

app.secret_key = "secret123key"
app.permanent_session_lifetime = timedelta(hours=1)

app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = True

Session(app)

socketio = SocketIO(app)

genai.configure(api_key="AQ.Ab8RN6L8XDmbpF1TsvIDQBTXg7NAVkQdMmpS6m-jSyirL1nc8w")

@app.after_request
def add_header(response):
    if request.path.endswith('favicon.ico'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(app.static_folder, 'favicon.ico')


@socketio.on("admin_join")
def handle_admin_join(data):
    room = f"{data['user_id']}room"
    join_room(room)
    emit("admin_join_success", {"url":"/admin_chat_access?user_id="+str(data["user_id"])}, room=request.sid)

@socketio.on("join_user_room") 
def handle_join_user(data):
    user_id = session.get('user_id')
    room = f"{user_id}room"
    join_room(room)
    emit("join_user_success", {"url": "/chats"}, room=request.sid)

@socketio.on("join_room") 
def handle_join(data):
    a_id = session.get('agent_id')
    agent = "Agent_" + str(a_id)
    room = f"{data['user_id']}room"
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT agent_asigned FROM chat WHERE room_id=%s", (room,))
    agent_check = cursor.fetchone()
    if not agent_check:
            return
    elif agent_check[0] == "Agent_None" or agent_check[0] is None:
        cursor.execute("UPDATE chat SET agent_asigned = %s WHERE room_id = %s", (agent, room))
        conn.commit()
    elif agent_check and agent == agent_check[0]:
        join_room(room)
        emit("join_success", {"url": "/agent_chat?user_id=" + str(data["user_id"])}, room=request.sid)
        cursor.close()
        conn.close()
        return
    elif agent_check and agent != agent_check[0]:
        emit("redirect", {'url': '/agent_dashboard'}, room=request.sid)
        cursor.close()
        conn.close()
        return  
    cursor.close()
    conn.close()
    join_room(room)
    emit(
        "join_success",
        {
            "url":"/agent_chat?user_id="+str(data["user_id"])
        },
        room=request.sid
    )
    

@socketio.on("chat_data")
def chat_data(data):
    room = f"{data['room_id']}"
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT role, message FROM chatbot_chats WHERE room_id=%s ORDER BY id ASC", (room,))
    history = cursor.fetchall()
    cursor.close()
    conn.close()
    emit("chat_history", [{"role": r, "message": m} for r, m in history], room=room)


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
            user_id = name.strip()
            room_id = name.strip() + "room"
            session['user_id'] = user_id
            session['room_id'] = room_id
            session['name'] = name
            cursor.execute("INSERT INTO chat (name,user_id,room_id) VALUES (%s,%s,%s)", (name,user_id,room_id))
            conn.commit()
            step = 2

        elif "country" in request.form:
            country = request.form["country"]
            session['country'] = country
            cursor.execute("UPDATE chat SET country = %s WHERE id = (SELECT id FROM (SELECT MAX(id) AS id FROM chat) AS t);", (country,))
            conn.commit()
            step = 3

        elif "mobile" in request.form:
            mobile = request.form["mobile"]
            session['mobile'] = mobile
            cursor.execute("UPDATE chat SET mobile = %s WHERE id = (SELECT id FROM (SELECT MAX(id) AS id FROM chat) AS t);", (mobile,))
            conn.commit()
            step = 4

        elif "email" in request.form:
            email = request.form["email"]
            session['email'] = email
            cursor.execute("UPDATE chat SET email = %s WHERE id = (SELECT id FROM (SELECT MAX(id) AS id FROM chat) AS t);", (email,))
            conn.commit()
            step = 5

        elif "service" in request.form:
            service = request.form["service"]
            session['service'] = service
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


@app.route("/Admin_login",methods=["GET"])
def Admin_login():
    return render_template("Admin_Portal_Analysis.html")
@app.route("/Admin_pannel",methods=["GET"])
def Admin_pannel():
    return render_template("Admin_pannel.html")

@app.route("/Admin_analysis",methods=["GET"])
def Admin_analysis():
    return render_template("Admin_Portal_Analysis.html")

@socketio.on("Admin_analysis")
def Admin_analysis_socket(data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM chat")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM agents")
    total_agents = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM chatbot_chats WHERE role = %s",("user",))
    total_user_chats = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM user_satisfied")
    satisfied = cursor.fetchone()[0]
    resolution = (satisfied/total_users)*100
    resolution_rate = int(resolution)
    socketio.emit("Admin_analysis_data",{"users":total_users,"user_chats":total_user_chats,"total_agents":total_agents,"resolution_rate":resolution_rate})


@auth.route("/agent_login",methods=["POST"])
def agent_login():
    if request.method == "POST":
        agent_login_name = str(request.form["Lagent_name"])
        agent_login_password = str(request.form["Lagent_password"])
        session["agent_id"] = agent_login_name
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT agent_name,agent_password from agents WHERE  BINARY agent_name=%s AND agent_password=%s",(agent_login_name,agent_login_password))
        checkp = cursor.fetchone()
        cursor.close()
        conn.close()
        if checkp:
            return render_template("agent.html")
        return render_template("login.html",msg = "invalid login")   
    return render_template("agent.html") 
        

app.register_blueprint(auth)

@app.route("/agent_dashboard",methods=["GET"])   
def agent_dashboard():
    return render_template("agent.html")


@socketio.on("user_satisfied")
def user_satisfied(data):
    user_id = session['user_id']
    user_name = session['name']
    room = session['room_id']
    email = session['email']
    service = session['service']
    mobile = session['mobile']
    country = session['country']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("select room_id from user_satisfied")
    rooms = cursor.fetchall()
    all_rooms = []
    for r in rooms:
        all_rooms.append(r[0])
    if room in all_rooms:
        return
    else:
        cursor.execute("INSERT INTO user_satisfied (user_id,user,user_email,service,room_id,mobile,country) VALUES(%s,%s,%s,%s,%s,%s,%s)",(user_id,user_name,email,service,room,mobile,country))
        conn.commit()
    cursor.close()
    conn.close()

@socketio.on("remove_satisfied_user")
def remove_satisfied_user():
    room = session['room_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_satisfied WHERE room_id=%s",(room,))
    conn.commit()
    cursor.close()
    conn.close()

@socketio.on("remove_agent")
def remove_agent(data):
    agent = str(data['agent_id'])
    room = str(data['room_id'])
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE chat SET agent_asigned = %s WHERE room_id = %s",("Agent_None",room))
    conn.commit()
    cursor.close()
    conn.close()
@socketio.on("satisfied_users")
def show_satisfied_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user,user_email,country,mobile,service FROM user_satisfied ORDER BY id DESC")
    s_users = cursor.fetchall()
    satisfied_users = []
    cursor.close()
    conn.close()
    if s_users:
        for s_user in s_users:
            satisfied_users.append({
                "user":s_user[0],
                "email": s_user[1],
                "country": s_user[2],
                "mobile": s_user[3],
                "service": s_user[4]    
            })
    socketio.emit("all_satisfied_users",satisfied_users)



@socketio.on("handover")
def handover(data):
    new_agent = "Agent_" + str(data['handover_agent'])
    room = str(data['room_id'])
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE chat SET agent_asigned = %s WHERE room_id = %s",(new_agent,room))
    conn.commit()
    cursor.close()
    conn.close()
    socketio.emit("handover_confirmation", {"room_id": room, "new_agent": new_agent})
    socketio.emit("refresh_agent",{ "room_id": room }, room=room)


@app.route("/chats",methods=["GET"])
def chats():
    return render_template("chats.html",user_id = session['user_id'])

@app.route("/admin_chat_access",methods=["GET"])
def admin_chat_access():
    user_id = request.args.get("user_id")
    room_id = f"{user_id}room"
    return render_template("Admin_chatbot_access.html",user_id = user_id,room_id = room_id)


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
    cursor.execute("SELECT agent_asigned from chat WHERE room_id = %s",(room,))
    agent = cursor.fetchone()
    cursor.execute("INSERT INTO chatbot_chats (role,message,user_id,room_id,agent_asigned) VALUES(%s,%s,%s,%s,%s)",(role2,agent_message,user_id,room,agent[0]))
    conn.commit()
    cursor.execute("SELECT message FROM chatbot_chats WHERE role = 'user' ORDER BY id DESC LIMIT 1")
    ress = cursor.fetchall()
    cursor.close()
    conn.close()
    socketio.emit("new_message",{"role":role2,"message":agent_message},room=room,)

@socketio.on('Admin_res')
def admin_res(resp):
    admin_message = resp["response"]
    user_id = resp['user_id']
    room = resp['room_id']
    role2 = "Admin"
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT agent_asigned from chat WHERE room_id = %s",(room,))
    agent = cursor.fetchone()
    cursor.execute("INSERT INTO chatbot_chats (role,message,user_id,room_id,agent_asigned) VALUES(%s,%s,%s,%s,%s)",(role2,admin_message,user_id,room,agent[0]))
    conn.commit()
    cursor.execute("SELECT message FROM chatbot_chats WHERE role = 'user' ORDER BY id DESC LIMIT 1")
    ress = cursor.fetchall()
    cursor.close()
    conn.close()
    socketio.emit("new_message",{"role":role2,"message":admin_message},room=room,)
    
@socketio.on('user_response')
def user_response(data):
    
    user_input = data["message"]
    user_id = session.get('user_id')
    room = session.get('room_id')
    agent = data['agent_id']
    role = "user"
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT agent_asigned from chat WHERE room_id = %s",(room,))
    agent = cursor.fetchone()
    cursor.execute("INSERT INTO chatbot_chats (role,message,user_id,room_id,agent_asigned) VALUES(%s,%s,%s,%s,%s)",(role,user_input,user_id,room,agent[0]))
    conn.commit()
    cursor.execute("SELECT message FROM chatbot_chats WHERE role = 'agent' ORDER BY id DESC LIMIT 1")
    mess2 = cursor.fetchall()
    cursor.close()
    conn.close()
    socketio.emit("new_message",{"role":role,"message":user_input},room=room)



@socketio.on('Agents')
def Agents(data):
    agent_ids = []
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT agent_name FROM agents")
    agent_data = cursor.fetchall()
    cursor.close()
    conn.close()
    if agent_data:
        for ag_id in agent_data:
            agent_ids.append(ag_id[0])
    socketio.emit("all_agents",agent_ids)





@socketio.on('USERS')
def user_info(data):
    # Yeh values login ke time set karni hongi
    users = []
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id,name,country,mobile,email,service,user_id,room_id,agent_asigned FROM chat ORDER BY id DESC;")
    user_information = cursor.fetchall()
    cursor.close()
    conn.close()

    if user_information:
        for user in user_information:
            users.append({
                "user_id": user[6] if user[6] else user[0],   # agar session empty hai to DB id use karo
                "name": user[1],
                "email": user[4],
                "service": user[5],
                "room_id": user[7] if user[7] else "N/A",
                "agent_asigned": user[8] if user[8] else "Agent_None"
            })  
    socketio.emit("all_users",users)
      # broadcast zaruri hai


  

@app.route("/login_page",methods=["GET"])
def login_page():
    return render_template("login.html")

@app.route("/signup_page",methods=["GET"])
def signup_page():
    return render_template("signup.html")

if __name__ == "__main__":
    socketio.run(app,debug=True)
