from flask import Flask,render_template,request,url_for,redirect,jsonify,Blueprint,session,make_response,flash,send_from_directory
from db import get_db_connection 
from email_validator import validate_email, EmailNotValidError
from flask_login import login_required,login_user,logout_user,current_user
from werkzeug.security import generate_password_hash,check_password_hash
from werkzeug.utils import secure_filename
from flask_session import Session
from datetime import timedelta
from flask_socketio import SocketIO,join_room,leave_room,send,emit
import uuid
import os
import json
import shutil
import time

# --------------------------------------------------------------
# RAG PIPELINE (PDF/DOCX -> LangChain -> HF Embeddings -> FAISS
# -> semantic search -> local Hugging Face LLM -> answer)
# --------------------------------------------------------------
from model import (
    extract_text_from_file,
    process_user_guide,
    generate_response_stream,
    stop_generation,
    remove_user_guide,
    ACTIVE_GUIDE_FILE,
    remove_specific_user_guide
)


app = Flask(__name__)
auth = Blueprint('auth',__name__)

app.secret_key = "secret123key"
app.permanent_session_lifetime = timedelta(hours=1)

app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = True

Session(app)

socketio = SocketIO(app)


# --------------------------------------------------------------
# COMPANY GUIDE UPLOAD CONFIGURATION
# --------------------------------------------------------------

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")

# --------------------------------------------------------------
# ACTIVE USER GUIDE INFORMATION
# --------------------------------------------------------------

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

GUIDE_METADATA_FILE = os.path.join(
    BASE_DIR,
    "active_user_guide.json"
)

ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )

# --------------------------------------------------------------
# SAVE ACTIVE GUIDE INFORMATION
# --------------------------------------------------------------

def save_active_guide(filename):

    guide_data = {

        "active": True,

        "filename": filename

    }


    with open(

        GUIDE_METADATA_FILE,

        "w",

        encoding="utf-8"

    ) as file:

        json.dump(

            guide_data,

            file

        )


# --------------------------------------------------------------
# GET ACTIVE GUIDE INFORMATION
# --------------------------------------------------------------

def get_active_guide():

    if not os.path.exists(
        GUIDE_METADATA_FILE
    ):

        return {

            "active": False,

            "filename": None

        }


    try:

        with open(

            GUIDE_METADATA_FILE,

            "r",

            encoding="utf-8"

        ) as file:

            return json.load(
                file
            )


    except Exception:

        return {

            "active": False,

            "filename": None

        }


# --------------------------------------------------------------
# DELETE ACTIVE GUIDE INFORMATION
# --------------------------------------------------------------

def delete_active_guide_metadata():

    if os.path.exists(
        GUIDE_METADATA_FILE
    ):

        os.remove(
            GUIDE_METADATA_FILE
        )



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
    emit("join_user_success", {"user_id": user_id,"room_id": room}, room=request.sid)


# ============================================================
# STOP GENERATION
# ============================================================

@socketio.on("stop_generation")
def handle_stop_generation(data):

    user_id = session.get("user_id")

    if not user_id:

        emit(
            "generation_stop_result",
            {
                "success": False,
                "message": "User session not found."
            },
            room=request.sid
        )

        return


    stopped = stop_generation(
        user_id
    )


    emit(

        "generation_stop_result",

        {

            "success": stopped,

            "message":

                "Stopping generation..."

                if stopped

                else

                "No active generation found."

        },

        room=request.sid

    )


# ============================================================
# BACKGROUND AI GENERATION
# ============================================================

def generate_bot_response(
    user_input,
    user_id,
    room
):

    full_answer = ""


    try:

        # ----------------------------------------------------
        # INFORM FRONTEND
        # ----------------------------------------------------

        socketio.emit(

            "generation_started",

            {},

            room=room

        )


        # ----------------------------------------------------
        # CHECK HUMAN AGENT STATUS
        # ----------------------------------------------------

        conn = get_db_connection()

        cursor = conn.cursor()


        cursor.execute(

            "SELECT agent_connect, agent_asigned "
            "FROM chat WHERE room_id=%s",

            (room,)

        )


        chat_data = cursor.fetchone()


        cursor.close()

        conn.close()


        # ----------------------------------------------------
        # HUMAN AGENT CONNECTED
        # ----------------------------------------------------

        if chat_data and chat_data[0] == 1:

            socketio.emit(

                "generation_finished",

                {

                    "status": "human_mode"

                },

                room=room

            )

            return


        # ----------------------------------------------------
        # STREAM CALLBACK
        # ----------------------------------------------------

        def stream_callback(full_text):

            socketio.emit(

                "bot_stream",

                {

                    "text": full_text

                },

                room=room

            )


        # ----------------------------------------------------
        # GENERATE RESPONSE
        # ----------------------------------------------------

        result = generate_response_stream(

            user_input,

            user_id,

            stream_callback

        )


        full_answer = result.get(

            "answer",

            ""

        )


        # ----------------------------------------------------
        # USER STOPPED GENERATION
        # ----------------------------------------------------

        if result.get("stopped"):

            socketio.emit(

                "generation_cancelled",

                {

                    "message":

                        "Generation stopped by user."

                },

                room=room

            )

            return


        # ----------------------------------------------------
        # SAVE COMPLETE BOT RESPONSE
        # ----------------------------------------------------

        if full_answer.strip():

            conn = get_db_connection()

            cursor = conn.cursor()


            cursor.execute(

                """
                INSERT INTO chatbot_chats
                (role,message,user_id,room_id,agent_asigned)

                VALUES(%s,%s,%s,%s,%s)
                """,

                (

                    "bot",

                    full_answer,

                    user_id,

                    room,

                    "bot"

                )

            )


            conn.commit()


            cursor.close()

            conn.close()


        # ----------------------------------------------------
        # GENERATION COMPLETE
        # ----------------------------------------------------

        socketio.emit(

            "generation_complete",

            {

                "answer": full_answer

            },

            room=room

        )


    except Exception as error:

        print(

            "AI generation error:",

            error

        )


        socketio.emit(

            "generation_error",

            {

                "message":

                    "An error occurred while generating the response."

            },

            room=room

        )


    finally:

        socketio.emit(

            "generation_finished",

            {},

            room=room

        )

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
        cursor.execute("UPDATE chat SET last_assist = %s WHERE room_id = %s", (agent, room))
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




@app.route("/", methods=["GET", "POST"])
def chatbot():

    # =====================================================
    # USER SUBMITS THE COMPLETE FORM
    # =====================================================

    if request.method == "POST":

        # -------------------------------------------------
        # GET ALL FORM DATA
        # -------------------------------------------------

        name = request.form.get(
            "name",
            ""
        ).strip()


        country = request.form.get(
            "country",
            ""
        ).strip()


        mobile = request.form.get(
            "mobile",
            ""
        ).strip()


        email = request.form.get(
            "email",
            ""
        ).strip()


        service = request.form.get(
            "service",
            ""
        ).strip()


        # -------------------------------------------------
        # VALIDATION
        # -------------------------------------------------

        if not all(
            [
                name,
                country,
                mobile,
                email,
                service
            ]
        ):

            return render_template(
                "index.html"
            )


        # =================================================
        # CREATE USER ID
        # =================================================

        user_id = uuid.uuid4().hex[:8]


        # =================================================
        # CREATE ROOM ID
        # =================================================

        room_id = user_id + "room"


        # =================================================
        # CREATE SESSION
        # =================================================

        session["user_id"] = user_id

        session["room_id"] = room_id

        session["name"] = name

        session["country"] = country

        session["mobile"] = mobile

        session["email"] = email

        session["service"] = service


        # =================================================
        # SAVE USER INFORMATION IN DATABASE
        # =================================================

        conn = get_db_connection()

        cursor = conn.cursor()


        cursor.execute(

            """
            INSERT INTO chat
            (
                name,
                user_id,
                room_id,
                country,
                mobile,
                email,
                service
            )

            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,

            (

                name,

                user_id,

                room_id,

                country,

                mobile,

                email,

                service

            )

        )


        conn.commit()


        cursor.close()

        conn.close()


        # =================================================
        # REDIRECT USER TO CHAT
        # =================================================

        return redirect(
            url_for("chats")
        )


    # =====================================================
    # SHOW THE USER INFORMATION PAGE
    # =====================================================

    return render_template(
        "index.html"
    )



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


@socketio.on("handover_to_bot")
def bot_handover(data):
    room = session['room_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE chat SET agent_connect=%s WHERE room_id=%s",(0,room))
    conn.commit()
    cursor.close()
    conn.close()



@app.route("/upload_guide", methods=["POST"])
def upload_guide():

    try:

        # ==========================================
        # CHECK FILE
        # ==========================================

        if "guide_file" not in request.files:

            return jsonify({

                "success": False,

                "message": "No file uploaded."

            })


        file = request.files["guide_file"]


        if file.filename == "":

            return jsonify({

                "success": False,

                "message": "Please select a file."

            })


        # ==========================================
        # ALLOWED FILE TYPES
        # ==========================================

        allowed_extensions = {

            ".pdf",

            ".docx",

            ".txt"

        }


        filename = secure_filename(
            file.filename
        )


        extension = os.path.splitext(
            filename
        )[1].lower()


        if extension not in allowed_extensions:

            return jsonify({

                "success": False,

                "message":
                    "Only PDF, DOCX and TXT files are allowed."

            })


        # ==========================================
        # CREATE UPLOAD DIRECTORY
        # ==========================================

        upload_folder = os.path.join(

            app.root_path,

            "uploads"

        )


        os.makedirs(

            upload_folder,

            exist_ok=True

        )


        # ==========================================
        # SAVE FILE
        # ==========================================

        filepath = os.path.join(

            upload_folder,

            filename

        )


        file.save(
            filepath
        )


        # ==========================================
        # GET APPEND OPTION
        # ==========================================

        append = (

            request.form.get(
                "append",
                "false"
            ).lower()

            == "true"

        )


        print(
            f"[UPLOAD] Append mode: {append}"
        )


        # ==========================================
        # EXTRACT TEXT
        # ==========================================

        user_guide_text = extract_text_from_file(
            filepath
        )


        if not user_guide_text.strip():

            return jsonify({

                "success": False,

                "message":
                    "Could not extract readable text from the file."

            })


        # ==========================================
        # PROCESS GUIDE INTO FAISS
        # ==========================================

        result = process_user_guide(

            user_guide_text,

            append=append

        )


        # ==========================================
        # STOP IF PROCESSING FAILED
        # ==========================================

        if not result.get("success"):

            return jsonify(
                result
            )


        # ==========================================
        # CREATE NEW GUIDE INFORMATION
        # ==========================================

        new_guide = {

            "filename": filename,

            "filepath": filepath,

            "uploaded_at": time.strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        }


        # ==========================================
        # APPEND MODE
        # ==========================================

        if append:


            guide_data = {

                "guides": []

            }


            # Load existing JSON data

            if os.path.exists(
                ACTIVE_GUIDE_FILE
            ):


                try:


                    with open(

                        ACTIVE_GUIDE_FILE,

                        "r",

                        encoding="utf-8"

                    ) as file_handle:


                        guide_data = json.load(
                            file_handle
                        )


                except Exception as error:


                    print(

                        "[UPLOAD] Error reading guide JSON:",

                        error

                    )


                    guide_data = {

                        "guides": []

                    }


            # Ensure correct structure

            if "guides" not in guide_data:


                guide_data = {

                    "guides": []

                }


            # Add new guide

            guide_data["guides"].append(

                new_guide

            )


        # ==========================================
        # REPLACE MODE
        # ==========================================

        else:


            guide_data = {

                "guides": [

                    new_guide

                ]

            }


        # ==========================================
        # SAVE ACTIVE GUIDE INFORMATION
        # ==========================================

        with open(

            ACTIVE_GUIDE_FILE,

            "w",

            encoding="utf-8"

        ) as file_handle:


            json.dump(

                guide_data,

                file_handle,

                indent=4

            )


        print(
            "[UPLOAD] Guide information saved successfully."
        )


        # ==========================================
        # RETURN SUCCESS
        # ==========================================

        return jsonify(

            result

        )


    except Exception as error:


        print(

            "UPLOAD GUIDE ERROR:",

            error

        )


        return jsonify({

            "success": False,

            "message": str(error)

        })


@app.route(
    "/remove_user_guide",
    methods=["POST"]
)
def remove_company_user_guide():

    try:

        result = remove_user_guide()


        return jsonify(
            result
        )


    except Exception as error:

        print(
            "REMOVE USER GUIDE ROUTE ERROR:",
            error
        )


        return jsonify({

            "success": False,

            "message": str(error)

        }), 500

@app.route("/remove_specific_user_guide",methods=["POST"])
def remove_specific_guide_route():

    try:

        data = request.get_json()


        if not data:

            return jsonify({

                "success": False,

                "message": "No data received."

            })


        filename = data.get(
            "filename"
        )


        if not filename:

            return jsonify({

                "success": False,

                "message": "Filename is required."

            })


        result = remove_specific_user_guide(

            filename

        )


        return jsonify(
            result
        )


    except Exception as error:


        print(

            "REMOVE SPECIFIC GUIDE ROUTE ERROR:",

            error

        )


        return jsonify({

            "success": False,

            "message": str(error)

        }), 500

@app.route("/guide_status", methods=["GET"])
def guide_status():

    try:

        if not os.path.exists(ACTIVE_GUIDE_FILE):

            return jsonify({

                "active": False,

                "guides": [],

                "count": 0

            })


        with open(

            ACTIVE_GUIDE_FILE,

            "r",

            encoding="utf-8"

        ) as file_handle:

            guide_data = json.load(file_handle)


        # ==========================================
        # NEW MULTIPLE GUIDES FORMAT
        # ==========================================

        if isinstance(guide_data, dict) and "guides" in guide_data:

            guides = guide_data.get("guides", [])


        # ==========================================
        # OLD SINGLE GUIDE FORMAT
        # Automatically support old JSON
        # ==========================================

        elif isinstance(guide_data, dict) and "filename" in guide_data:

            guides = [

                guide_data

            ]


        else:

            guides = []


        return jsonify({

            "active": len(guides) > 0,

            "guides": guides,

            "count": len(guides)

        })


    except Exception as error:

        print(

            "GUIDE STATUS ERROR:",

            error

        )


        return jsonify({

            "active": False,

            "guides": [],

            "count": 0,

            "message": str(error)

        }), 500
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
    cursor.execute("SELECT COUNT(*) FROM chat WHERE satisfied=%s",(1,))
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
    room = session['room_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE chat SET satisfied=%s, satisfied_agent=agent_asigned WHERE room_id=%s",(1,room))
    conn.commit()
    cursor.close()
    conn.close()

@socketio.on("remove_satisfied_user")
def remove_satisfied_user():
    remove_placeholder = "Agent_None"
    room = session['room_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE chat SET satisfied=%s, satisfied_agent=%s WHERE room_id=%s",(0,remove_placeholder,room))
    conn.commit()
    cursor.close()
    conn.close()

@socketio.on("remove_agent")
def remove_agent(data):
    room = str(data['room_id'])
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE chat SET agent_asigned = %s WHERE room_id = %s",("bot",room))
    conn.commit()
    cursor.execute("UPDATE chat SET agent_connect=%s WHERE room_id=%s",(0,room))
    conn.commit()
    cursor.close()
    conn.close()
    socketio.emit("refresh_removed_agent",{ "room_id": room }, room=room)
@socketio.on("satisfied_users")
def show_satisfied_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name,email,country,mobile,service,satisfied_agent FROM chat WHERE satisfied=%s",(1,))
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
                "service": s_user[4],
                "Satisfied_By": s_user[5]
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
    cursor.execute("UPDATE chat SET agent_connect=%s WHERE room_id=%s",(1,room))
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

@socketio.on("agent_connect")
def agent_need(data):
    room = session.get('room_id')
    removed = "Agent_None"
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE chat SET agent_connect=%s,agent_asigned=%s WHERE room_id=%s",(1,removed,room))
    conn.commit()
    cursor.close()
    conn.close()
    



# ============================================================
# USER RESPONSE
# ============================================================

@socketio.on("user_response")
def user_response(data):

    user_input = data.get(
        "message",
        ""
    ).strip()


    user_id = session.get(
        "user_id"
    )


    room = session.get(
        "room_id"
    )


    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    if not user_input:

        return


    if not user_id or not room:

        emit(

            "generation_error",

            {

                "message":
                    "User session expired. Please refresh."

            },

            room=request.sid

        )

        return


    # --------------------------------------------------------
    # SAVE USER MESSAGE
    # --------------------------------------------------------

    conn = get_db_connection()

    cursor = conn.cursor()


    cursor.execute(

        "SELECT agent_asigned, agent_connect "
        "FROM chat WHERE room_id=%s",

        (room,)

    )


    chat_info = cursor.fetchone()


    agent_name = (

        chat_info[0]

        if chat_info

        else "Agent_None"

    )


    cursor.execute(

        """
        INSERT INTO chatbot_chats
        (role,message,user_id,room_id,agent_asigned)

        VALUES(%s,%s,%s,%s,%s)
        """,

        (

            "user",

            user_input,

            user_id,

            room,

            agent_name

        )

    )


    conn.commit()


    cursor.close()

    conn.close()


    # --------------------------------------------------------
    # DISPLAY USER MESSAGE IMMEDIATELY
    # --------------------------------------------------------

    socketio.emit(

        "new_message",

        {

            "role": "user",

            "message": user_input

        },

        room=room

    )


    # --------------------------------------------------------
    # START AI IN BACKGROUND
    # --------------------------------------------------------

    socketio.start_background_task(

        generate_bot_response,

        user_input,

        user_id,

        room

    )


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


@socketio.on('Admin_USERS_access')
def user_info(data):
    # Yeh values login ke time set karni hongi
    users = []
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id,name,country,mobile,email,service,user_id,room_id,agent_asigned,last_assist FROM chat ORDER BY id DESC;")
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
                "agent_asigned": user[8] if user[8] else "Agent_None",
                "last_assist": user[9] if user[9] else "Agent_None"
            })  
    socketio.emit("admin_all_users_access",users)


@socketio.on('USERS')
def user_info(data):
    # Yeh values login ke time set karni hongi
    users = []
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id,name,country,mobile,email,service,user_id,room_id,agent_asigned,last_assist FROM chat WHERE agent_connect=%s ORDER BY id DESC;",(1))
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
                "agent_asigned": user[8] if user[8] else "Agent_None",
                "last_assist": user[9] if user[9] else "Agent_None"
            })  
    socketio.emit("all_users",users)
      # broadcast zaruri hai


@app.route("/company_knowledgebase",methods=["GET"])
def company_knowledgebase():
    return render_template("Company_knowledgebase.html")

@app.route("/login_page",methods=["GET"])
def login_page():
    return render_template("login.html")

@app.route("/signup_page",methods=["GET"])
def signup_page():
    return render_template("signup.html")

if __name__ == "__main__":
    socketio.run(app,debug=True,use_reloader=False)
