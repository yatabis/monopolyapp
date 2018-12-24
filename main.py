from base64 import b64encode
import io
import json
import os
from uuid import uuid4

from bottle import get, post, request, run
from bottle import jinja2_template as render
from bottle import TEMPLATE_PATH
from pprint import pprint
import psycopg2
from psycopg2.extras import DictCursor
import qrcode
import requests

CAT = os.environ.get('CHANNEL_ACCESS_TOKEN')
HEADER = {'Contetnt-Type': 'application/json', 'Authorization': f"Bearer {CAT}"}
DATABASE = os.environ.get('DATABASE_URL')
TEMPLATE_PATH.append("templates/")
OK_RESPONSE = {'status_code': 200, 'message': "OK"}


# database
def connect_db():
    return psycopg2.connect(DATABASE)


@get('/api/player/<line_id>')
def get_player(line_id=None):
    with connect_db() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute('select * from player where line_id = %s', (line_id,))
            player = dict(cur.fetchone())
    return json.dumps(player, ensure_ascii=False)


@get('/api/room/<room_id>/player')
def get_members(room_id=None):
    with connect_db() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute('select * from player where room_id = %s', (room_id,))
            members = []
            for row in cur.fetchall():
                members.append(dict(row))
    members.sort(key=lambda x: x.pop('joined'))
    return json.dumps(members, ensure_ascii=False)


@post('/api/room/<room_id>/parent')
def set_parent(room_id=None):
    parent = request.json['parent']
    with connect_db() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute('update room set parent = %s where room_id = %s;', (parent, room_id))


@post('/api/player')
def set_player():
    line_id = request.json.get('line_id', "")
    line_name = get_display_name(line_id)
    room_id = request.json.get('room_id', "")
    position = request.json.get('position', 'child')
    check = json.loads(get_player(line_id))
    with connect_db() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            if len(check) == 0:
                cur.execute('insert into player (line_id, line_name, room_id, position) values (%s, %s, %s, %s);',
                            (line_id, line_name, room_id, position))
                return OK_RESPONSE
            elif check['room_id'] == "":
                cur.execute('update player set room_id = %s, position = %s;', (room_id, position))
                return OK_RESPONSE
            else:
                return {'status_code': 409, 'message': "他のルームでプレイ中のため入室できません。"}


# LINE API
def push_text(to, text):
    ep = "https://api.line.me/v2/bot/message/push"
    body = {'to': to, 'messages': [{'type': 'text', 'text': text}]}
    return requests.post(ep, data=json.dumps(body, ensure_ascii=False).encode('utf-8'), headers=HEADER)


@get('/api/display-name/<line_id>')
def get_display_name(line_id=None):
    if line_id is None:
        return "line_id is None."
    ep = f"https://api.line.me/v2/bot/profile/{line_id}"
    req = requests.get(ep, headers=HEADER)
    if req.status_code == 200:
        return req.json().get('displayName')
    else:
        return req.json()


# functions
def create_new_room():
    room_id = str(b64encode(str(uuid4()).encode('utf-8')))[2:-1].lower()
    room_qr = qrcode.make(f"line://app/1629635023-JwWZbqzz?room={room_id}").get_image()
    qr_img = io.BytesIO()
    room_qr.save(qr_img, format='PNG')
    data = str(b64encode(qr_img.getvalue()))[2:-1]
    with connect_db() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute('insert into room (room_id, state) values (%s, %s);', (room_id, "starting"))
    return room_id, data


# callback
@get('/make-room')
def make_room():
    room_id, qr_code = create_new_room()
    title = f"ルーム{room_id[:6]}"
    return render('room.html', title=title, room_id=room_id, qr_code=qr_code)


@get('/join-room')
def join_room():
    room_id = request.query.get('room')
    title = f"ルーム{room_id[:6]}"
    return render('join.html', title=title, room_id=room_id)


if __name__ == '__main__':
    run(host='0.0.0.0', port=int(os.environ.get('PORT', 443)))
