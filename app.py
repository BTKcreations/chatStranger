from flask import Flask, render_template, request, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room
import random
import string
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  # 1MB max-length
socketio = SocketIO(app, 
                   async_mode='gevent',
                   ping_timeout=60,
                   ping_interval=25,
                   cors_allowed_origins="*",
                   logger=True,
                   engineio_logger=True)

# Store waiting users and active connections (with a maximum limit)
MAX_WAITING_USERS = 100
MAX_ACTIVE_CONNECTIONS = 50
online_users = 0
waiting_users = 0
active_connections = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.svg')

@socketio.on('connect')
def handle_connect():
    global online_users
    online_users += 1
    emit('user_count_update', {'online': online_users, 'waiting': waiting_users}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    global online_users
    online_users -= 1
    emit('user_count_update', {'online': online_users, 'waiting': waiting_users}, broadcast=True)
    try:
        sid = request.sid
        # Remove from waiting list
        waiting_users[:] = [u for u in waiting_users if u['sid'] != sid]
        
        # Handle active connections
        rooms_to_remove = []
        for room_id, users in active_connections.items():
            if users['user1']['sid'] == sid or users['user2']['sid'] == sid:
                emit('stranger_disconnected', to=room_id)
                rooms_to_remove.append(room_id)
                
        for room_id in rooms_to_remove:
            del active_connections[room_id]
    except Exception as e:
        app.logger.error(f"Error in handle_disconnect: {str(e)}")

@socketio.on('join_waiting_room')
def handle_join_waiting_room(data):
    try:
        global waiting_users
        waiting_users += 1
        emit('user_count_update', {'online': online_users, 'waiting': waiting_users}, broadcast=True)
        user_name = data.get('name', '').strip()[:50]  # Limit username length
        sid = request.sid  # Use request.sid instead of data['sid']
        
        if not user_name:
            emit('error', {'message': 'Invalid username'})
            return
            
        # Clean up disconnected users
        waiting_users[:] = [u for u in waiting_users if u['sid'] != sid]
        
        # Check waiting room capacity
        if len(waiting_users) >= MAX_WAITING_USERS:
            emit('error', {'message': 'Server is busy. Please try again later.'})
            return
        
        if len(waiting_users) > 0:
            # Match with a random waiting user
            stranger = random.choice(waiting_users)
            waiting_users.remove(stranger)
            
            # Check active connections capacity
            if len(active_connections) >= MAX_ACTIVE_CONNECTIONS:
                emit('error', {'message': 'Server is busy. Please try again later.'})
                return
                
            # Generate a unique room ID
            room_id = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            
            # Add both users to the room
            join_room(room_id)
            emit('matched', {
                'room': room_id,
                'stranger_name': stranger['name']
            })
            
            join_room(room_id, sid=stranger['sid'])
            emit('matched', {
                'room': room_id,
                'stranger_name': user_name
            }, to=stranger['sid'])
            
            # Store the connection
            active_connections[room_id] = {
                'user1': {'sid': sid, 'name': user_name},
                'user2': {'sid': stranger['sid'], 'name': stranger['name']}
            }
        else:
            # Add user to waiting list
            waiting_users.append({'sid': sid, 'name': user_name})
            emit('waiting')
    except Exception as e:
        app.logger.error(f"Error in join_waiting_room: {str(e)}")
        emit('error', {'message': 'An error occurred. Please try again.'})

@socketio.on('send_message')
def handle_message(data):
    try:
        room = data.get('room')
        message = data.get('message', '').strip()[:500]  # Limit message length
        sender = data.get('sender', '').strip()[:50]  # Limit sender name length
        
        if not all([room, message, sender]):
            return
            
        if room in active_connections:
            emit('new_message', {
                'message': message,
                'sender': sender
            }, to=room)
    except Exception as e:
        app.logger.error(f"Error in handle_message: {str(e)}")

@socketio.on('typing')
def handle_typing(data):
    try:
        room = data.get('room')
        username = data.get('username', '').strip()[:50]
        if room and username and room in active_connections:
            emit('typing_status', {
                'username': username,
                'isTyping': True
            }, to=room)
    except Exception as e:
        app.logger.error(f"Error in handle_typing: {str(e)}")

@socketio.on('stop_typing')
def handle_stop_typing(data):
    try:
        room = data.get('room')
        username = data.get('username', '').strip()[:50]
        if room and username and room in active_connections:
            emit('typing_status', {
                'username': username,
                'isTyping': False
            }, to=room)
    except Exception as e:
        app.logger.error(f"Error in handle_stop_typing: {str(e)}")

@socketio.on('leave_waiting_room')
def handle_leave_waiting_room():
    global waiting_users
    waiting_users -= 1
    emit('user_count_update', {'online': online_users, 'waiting': waiting_users}, broadcast=True)

@socketio.on('matched')
def handle_matched(data):
    global waiting_users
    waiting_users -= 2  # Both users are no longer waiting
    emit('user_count_update', {'online': online_users, 'waiting': waiting_users}, broadcast=True)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
