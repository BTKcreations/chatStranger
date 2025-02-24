from flask import Flask, render_template, request, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room
import secrets
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
socketio = SocketIO(app, 
                   cors_allowed_origins="*",
                   async_mode='threading',
                   ping_timeout=60,
                   ping_interval=25,
                   logger=True,
                   engineio_logger=True)

# Global variables for user tracking
online_users = 0
waiting_users = []  # List of dictionaries containing user info
user_rooms = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

@socketio.on('connect')
def handle_connect():
    global online_users
    online_users += 1
    emit('user_count_update', {'online': online_users, 'waiting': len(waiting_users)}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    global online_users, waiting_users
    online_users = max(0, online_users - 1)
    
    # Remove user from waiting list if they were waiting
    sid = request.sid
    waiting_users[:] = [u for u in waiting_users if u['sid'] != sid]
    
    # Leave room if user was in one
    if sid in user_rooms:
        room = user_rooms[sid]
        leave_room(room)
        del user_rooms[sid]
        
        # Notify other user in room
        emit('chat_ended', room=room, broadcast=True)
    
    emit('user_count_update', {'online': online_users, 'waiting': len(waiting_users)}, broadcast=True)

@socketio.on('join_waiting_room')
def handle_join_waiting(data):
    try:
        global waiting_users
        sid = request.sid
        name = data.get('name', '').strip()[:50]  # Limit username length
        
        # Remove existing entry if user is already waiting
        waiting_users[:] = [u for u in waiting_users if u['sid'] != sid]
        
        # Add user to waiting list
        user_data = {'sid': sid, 'name': name}
        waiting_users.append(user_data)
        
        # Try to match with another waiting user
        if len(waiting_users) >= 2:
            user1 = waiting_users.pop(0)
            user2 = waiting_users.pop(0)
            
            # Create a room
            room = secrets.token_hex(8)
            join_room(room, sid=user1['sid'])
            join_room(room, sid=user2['sid'])
            
            # Store room information
            user_rooms[user1['sid']] = room
            user_rooms[user2['sid']] = room
            
            # Notify users
            emit('matched', {'room': room, 'stranger_name': user2['name']}, to=user1['sid'])
            emit('matched', {'room': room, 'stranger_name': user1['name']}, to=user2['sid'])
        
        emit('user_count_update', {'online': online_users, 'waiting': len(waiting_users)}, broadcast=True)
        
    except Exception as e:
        print(f"Error in join_waiting_room: {str(e)}")
        emit('error', {'message': 'An error occurred. Please try again.'})

@socketio.on('send_message')
def handle_message(data):
    room = data.get('room')
    message = data.get('message', '').strip()[:500]  # Limit message length
    sender = data.get('sender', '').strip()[:50]  # Limit sender name length
    
    if room and message:
        emit('new_message', {'message': message, 'sender': sender}, room=room)

@socketio.on('typing')
def handle_typing(data):
    room = data.get('room')
    username = data.get('username', '').strip()[:50]  # Limit username length
    
    if room and username:
        emit('typing_status', {'username': username, 'isTyping': True}, room=room)

@socketio.on('stop_typing')
def handle_stop_typing(data):
    room = data.get('room')
    username = data.get('username', '').strip()[:50]  # Limit username length
    
    if room and username:
        emit('typing_status', {'username': username, 'isTyping': False}, room=room)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True)
