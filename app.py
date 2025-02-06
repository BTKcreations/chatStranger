from flask import Flask, render_template
from flask_socketio import SocketIO, emit, join_room, leave_room
import random
import string
from engineio.async_drivers import threading

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
socketio = SocketIO(app, async_mode='threading')

# Store waiting users and active connections
waiting_users = []
active_connections = {}

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('join_waiting_room')
def handle_join_waiting_room(data):
    user_name = data['name']
    sid = data['sid']
    
    # Remove user from waiting list if they were already there
    waiting_users[:] = [u for u in waiting_users if u['sid'] != sid]
    
    if len(waiting_users) > 0:
        # Match with a random waiting user
        stranger = random.choice(waiting_users)
        waiting_users.remove(stranger)
        
        # Generate a unique room ID
        room_id = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        
        # Add both users to the room
        join_room(room_id)
        emit('matched', {
            'room': room_id,
            'stranger_name': stranger['name']
        }, to=sid)
        
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

@socketio.on('send_message')
def handle_message(data):
    room = data['room']
    message = data['message']
    emit('new_message', {
        'message': message,
        'sender': data['sender']
    }, to=room)

@socketio.on('disconnect')
def handle_disconnect():
    # Remove from waiting list
    waiting_users[:] = [u for u in waiting_users if u['sid'] != request.sid]
    
    # Handle active connections
    for room_id, users in active_connections.items():
        if users['user1']['sid'] == request.sid or users['user2']['sid'] == request.sid:
            emit('stranger_disconnected', to=room_id)
            del active_connections[room_id]
            break

if __name__ == '__main__':
    socketio.run(app, debug=True)
