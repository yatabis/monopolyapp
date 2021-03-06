from base64 import b64encode
import io
import json
import os
from uuid import uuid4

from bottle import get, post, request, run, route, static_file
from bottle import jinja2_template as render
from bottle import TEMPLATE_PATH
from PIL import Image
from pprint import pprint
import psycopg2
from psycopg2.extras import DictCursor
import qrcode
import requests

CAT = os.environ.get('CHANNEL_ACCESS_TOKEN')
MASTER = os.environ.get('MASTER')
HEADER = {'Content-Type': 'application/json', 'Authorization': f"Bearer {CAT}"}
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
    push_text(parent, f"ルーム{room_id[:6]}を作成しました。")


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
                push_text(line_id, f"ルーム{room_id[:6]}に入室しました。")
                link_richmenu(line_id, position)
                return OK_RESPONSE
            elif check['room_id'] == "":
                cur.execute('update player set room_id = %s, position = %s;', (room_id, position))
                push_text(line_id, f"ルーム{room_id[:6]}に入室しました。")
                link_richmenu(line_id, position)
                return OK_RESPONSE
            else:
                return {'status_code': 409, 'message': "他のルームでプレイ中のため入室できません。"}


# LINE API
@post('/api/line/push')
def push_text(to=None, text=None):
    if text is None:
        text = request.json.get('text', "メッセージがありません。")
    if to is None:
        to = request.json.get('to', MASTER)
        text = "プッシュメッセージの送信に失敗しました。"
    ep = "https://api.line.me/v2/bot/message/push"
    body = {'to': to, 'messages': [{'type': 'text', 'text': text}]}
    return requests.post(ep, data=json.dumps(body, ensure_ascii=False).encode('utf-8'), headers=HEADER)


@post('/api/line/reply')
def reply_text(token=None, text=None):
    if text is None:
        text = request.json.get('text', "メッセージがありません。")
    if token is None:
        token = request.json.get('replyToken', "TokenError")
    if token == "TokenError":
        push_text(MASTER, "リプライメッセージの送信に失敗しました。")
    ep = "https://api.line.me/v2/bot/message/reply"
    body = {'replyToken': token, 'messages': [{'type': 'text', 'text': text}]}
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
def get_image_data(img, fmt='PNG'):
    data = io.BytesIO()
    img.save(data, format=fmt)
    return str(b64encode(data.getvalue()))[2:-1]


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


def link_richmenu(line_id, position):
    richmenu_id = {'parent': "",
                   'child': "richmenu-fd8b0d6d96122d2c8b9bc9a6d892fdc4"}
    ep = f"https://api.line.me/v2/bot/user/{line_id}/richmenu/{richmenu_id[position]}"
    return requests.post(ep, headers=HEADER)


def unlink_richmenu(line_id):
    ep = f"https://api.line.me/v2/bot/user/{line_id}/richmenu"
    return requests.delete(ep, headers=HEADER)


# callback
@route('/images/<filename:path>')
def load_image(filename):
    return static_file(filename, root='./images')


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


@get('/memory-bank')
def memory_bank():
    return render('memorybank.html')


@post('/line/callback')
def line_callback():
    for event in request.json.get('events'):
        pprint(event)
        if event['type'] == 'postback':
            reply_token = event['replyToken']
            if event['postback']['data'] == 'deal=payee':
                reply_text(reply_token, "受取人にセットしました")
            elif event['postback']['data'] == 'deal=payer':
                reply_text(reply_token, "支払人にセットしました")


if __name__ == '__main__':
    run(host='0.0.0.0', port=int(os.environ.get('PORT', 443)))
