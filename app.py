import random
import string
from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, leave_room, emit
import eventlet

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

# Dictionary to store waiting users and their session IDs
waiting_users = []
# Dictionary to map session IDs to rooms
user_rooms = {}

# Function to generate a random nickname
def generate_random_nickname():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

# Route for the homepage
@app.route('/')
def index():
    return render_template('index.html')

# Handle user joining the chat
@socketio.on('join')
def on_join(data):
    username = generate_random_nickname()
    sid = request.sid  # Get the session ID of the connected client

    app.logger.info(f"User joined: {username} with session ID: {sid}")

    if waiting_users:
        # Pair with the first waiting user
        partner_sid = waiting_users.pop(0)
        room = f"room-{sid}-{partner_sid}"  # Create a unique room name
        user_rooms[sid] = room
        user_rooms[partner_sid] = room

        join_room(room)
        join_room(partner_sid)

        # Notify both users they are paired
        emit('paired', {'room': room, 'partner': username}, to=partner_sid)
        emit('paired', {'room': room, 'partner': 'Anonymous'}, to=sid)

        # Send a "waiting" state update to the first user if they're still waiting
        emit('waiting', {'message': 'You are now paired! You can start chatting.'}, to=partner_sid)
    else:
        # Add user to waiting queue
        waiting_users.append(sid)
        emit('waiting', {'message': 'Waiting for a partner...'}, to=sid)

    app.logger.info(f"Current waiting users: {waiting_users}")

# Handle sending a message
@socketio.on('message')
def handle_message(data):
    sid = request.sid
    room = user_rooms.get(sid)

    if room:
        message = data.get('message')
        partner_sid = None
        
        # Find the partner's session ID from the room
        for s, r in user_rooms.items():
            if r == room and s != sid:
                partner_sid = s
                break

        if partner_sid:
            # Emit the message to the other user (partner)
            emit('message', {'message': message, 'from': 'You'}, room=partner_sid)
            # Emit the message to the sender (sender sees 'Partner' message)
            emit('message', {'message': message, 'from': 'Partner'}, room=sid)
        else:
            # If no partner found, it might indicate an issue with the room state
            emit('error', {'message': 'No partner found in the room.'}, to=sid)
    else:
        emit('error', {'message': 'You are not connected to a room.'}, to=sid)

# Handle user disconnect
@app.route('/disconnect')
def on_disconnect():
    sid = request.sid
    # Check if user is paired
    if sid in user_rooms:
        room = user_rooms[sid]
        # Get all users in the room
        room_users = [user for user, user_sid in user_rooms.items() if user_sid == room]
        # Ensure there's more than one user
        if len(room_users) > 1:
            partner_sid = [s for s in user_rooms.values() if s != sid][0]  # Get partner session ID
            # Notify partner that the user has left
            socketio.emit('partner_left', {'message': 'Your partner has left the chat.'}, room=partner_sid)
        # Remove the user from the room
        del user_rooms[sid]


# Handle reconnect for a user to join again after disconnect
@socketio.on('rejoin')
def on_rejoin():
    sid = request.sid
    if sid not in waiting_users:
        # The user is not already waiting, so they should be paired immediately
        if waiting_users:
            partner_sid = waiting_users.pop(0)
            room = f"room-{sid}-{partner_sid}"  # Create a unique room name
            user_rooms[sid] = room
            user_rooms[partner_sid] = room

            join_room(room)
            join_room(partner_sid)

            # Notify both users they are paired
            emit('paired', {'room': room, 'partner': 'Anonymous'}, to=partner_sid)
            emit('paired', {'room': room, 'partner': 'Anonymous'}, to=sid)

            emit('waiting', {'message': 'You are now paired! You can start chatting.'}, to=partner_sid)
        else:
            # Add the user to the waiting list
            waiting_users.append(sid)
            emit('waiting', {'message': 'Waiting for a partner...'}, to=sid)
    else:
        # If they are already waiting, just let them know they're still waiting
        emit('waiting', {'message': 'Still waiting for a partner...'}, to=sid)

if __name__ == '__main__':
    socketio.run(app)
