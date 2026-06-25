🤖 AI Customer Support Chatbot

An AI-powered customer support chatbot built with Flask, Google Gemini AI, MySQL, and Socket.IO. The application collects user information, allows customers to chat in real time, and provides an agent dashboard for human support when needed.

🚀 Features
AI-powered chatbot using Google Gemini
Real-time communication with Socket.IO
Customer information collection
Agent login and signup system
Live customer-agent chat support
Session management
MySQL database integration
Responsive web interface
🛠️ Technologies Used
Backend
Python
Flask
Flask-SocketIO
Flask-Session
MySQL (PyMySQL)
Google Gemini API
Frontend
HTML
CSS
JavaScript
Database
MySQL
📂 Project Structure
chatbot/
│
├── chatbot.py              # Main Flask application
├── db.py                   # Database connection
├── requirements.txt        # Project dependencies
│
├── static/
│   └── style.css
│
├── templates/
│   ├── index.html
│   ├── chats.html
│   ├── login.html
│   ├── signup.html
│   ├── agent.html
│   └── agent_chatbot.html
│
└── README.md
⚙️ Installation
1. Clone the Repository
git clone https://github.com/gopalkashyap19/chatbot_github.git

cd ai-customer-chatbot
2. Create Virtual Environment
python -m venv venv

Activate:

Windows
venv\Scripts\activate
Linux / Mac
source venv/bin/activate
3. Install Dependencies
pip install -r requirements.txt

You may also need:

pip install flask
pip install pymysql
pip install flask-socketio
pip install flask-session
pip install google-generativeai
pip install email-validator
pip install flask-jwt-extended
🗄️ Database Setup

Create a MySQL database:

CREATE DATABASE aichatbot;
Required Tables
chat
CREATE TABLE chat (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100),
    country VARCHAR(100),
    mobile VARCHAR(20),
    email VARCHAR(255),
    service VARCHAR(255),
    user_id VARCHAR(255),
    room_id VARCHAR(255)
);
agents
CREATE TABLE agents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    agent_name VARCHAR(100),
    agent_email VARCHAR(255),
    agent_password VARCHAR(255)
);
chatbot_chats
CREATE TABLE chatbot_chats (
    id INT AUTO_INCREMENT PRIMARY KEY,
    role VARCHAR(50),
    message TEXT,
    user_id VARCHAR(255),
    room_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
🔑 Configure Gemini API

Inside chatbot.py, replace the API key with your own:

genai.configure(api_key="YOUR_GEMINI_API_KEY")

Get your API key from:

Google AI Studio

▶️ Run the Application
python chatbot.py

Application will start on:

http://127.0.0.1:5000
👨‍💼 Agent Workflow
Agent creates an account.
Agent logs into the dashboard.
Customers start conversations.
Agent views active users.
Agent joins the customer room.
Real-time messages are exchanged through Socket.IO.
👤 Customer Workflow
Enter name.
Provide country.
Enter mobile number.
Enter email.
Select service requirement.
Start chat session.
Receive AI and agent assistance.
🔄 Real-Time Communication

Socket.IO events used:

join_room
user_response
agent_res
USERS
all_users
new_message

These events enable instant communication between customers and support agents.

📸 Screens Included
Customer Information Form
Customer Chat Interface
Agent Login
Agent Dashboard
Agent Chat Window

🔒 Future Improvements
Password hashing using Werkzeug
JWT Authentication
Chat history management
Multi-agent support
Email notifications
User authentication
Admin dashboard
AI conversation memory
Analytics and reporting

🤝 Contributing

Contributions, feature requests, and improvements are welcome.

Fork the repository
Create a feature branch
Commit changes
Open a Pull Request
📜 License

This project is developed for learning and educational purposes. Feel free to modify and extend it according to your requirements.

⭐ If you found this project useful, don't forget to star the repository! ⭐
