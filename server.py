"""
HaUI Counseling Chat Server
Flask + Socket.IO real-time chat
"""

from flask import Flask, send_from_directory, request
from flask_socketio import SocketIO, emit
import os, time, threading, re

app = Flask(__name__, static_folder='public', static_url_path='')
app.config['SECRET_KEY'] = 'haui-secret-2024'
socketio = SocketIO(app, cors_allowed_origins="*")

# ===================== STATE =====================
# Persistent student sessions (survives refresh)
# { sessionId: { sessionId, socketSid, name, studentId, className, issue, branch, status, counselorSid, joinedAt, messages[] } }
sessions = {}

# Map current socket sid -> sessionId
sid_to_session = {}

# Counselors online
# { sid: { name } }
counselors = {}

# Bot delay before responding (seconds)
BOT_DELAY = 15

# ===================== BOT RESPONSES =====================

academic_responses = {
    'greeting': 'Xin chào! Tôi là Bot Hỗ trợ Học tập của HaUI. Yêu cầu của bạn đang được xử lý chờ trong giây lát nhé!',
    'keywords': {
        r'lịch học|lich hoc|thời khóa biểu|thoi khoa bieu|tkb': 'Bạn có thể tra cứu Thời khóa biểu tại cổng thông tin sinh viên: https://sv.haui.edu.vn hoặc liên hệ Phòng Đào tạo (tầng 1, nhà A1). Hotline: 024.3765.5121.',
        r'lịch thi|lich thi|thi cuối kỳ|thi cuoi ky|thi giữa kỳ|đề thi|de thi': 'Lịch thi được cập nhật trên cổng SV: https://sv.haui.edu.vn. Bạn nên kiểm tra email trường thường xuyên. Nếu có trùng lịch thi, hãy làm đơn tại Phòng Đào tạo trước 1 tuần.',
        r'đăng ký|dang ky|đăng ký môn|dang ky mon|đăng ký học phần|hoc phan': 'Đăng ký môn học online tại: https://sv.haui.edu.vn. Thời gian mở đăng ký thường vào đầu mỗi kỳ. Lưu ý: kiểm tra môn tiên quyết trước khi đăng ký.',
        r'học phí|hoc phi|đóng tiền|dong tien|miễn giảm|mien giam': 'Học phí đóng qua ngân hàng theo mã sinh viên. Bạn xem thông tin chi tiết tại Phòng Kế hoạch - Tài chính (tầng 2, nhà A1). Nếu thuộc diện miễn giảm, nộp giấy tờ tại Phòng CTSV.',
        r'học bổng|hoc bong|khen thưởng|khen thuong': 'Học bổng được xét theo từng kỳ dựa trên GPA. Điều kiện cụ thể xem tại mục Thông báo trên website trường. Liên hệ Phòng CTSV để biết thêm.',
        r'giấy tờ|giay to|xác nhận|xac nhan|bằng tốt nghiệp|bang tot nghiep|bảng điểm|bang diem': 'Bạn có thể xin giấy xác nhận sinh viên, bảng điểm, giấy giới thiệu tại Phòng Đào tạo. Thời gian trả kết quả: 3-5 ngày làm việc.',
        r'chuyển ngành|chuyen nganh|chuyển lớp|chuyen lop|thôi học|thoi hoc|bảo lưu|bao luu': 'Các thủ tục chuyển ngành, bảo lưu: nộp đơn tại Phòng Đào tạo kèm lý do. Thời hạn bảo lưu tối đa 2 kỳ. Liên hệ cố vấn học tập để được hướng dẫn.',
        r'điểm|diem|gpa|kết quả|ket qua|tra cứu điểm|tra cuu diem': 'Điểm học tập tra cứu tại https://sv.haui.edu.vn mục "Kết quả học tập". Nếu thắc mắc về điểm, liên hệ giảng viên bộ môn hoặc Phòng Đào tạo.',
        r'kí túc|ki tuc|ktx|ở nội trú|noi tru': 'Đăng ký KTX tại Trung tâm Quản lý KTX (khuôn viên trường). Lưu ý: ưu tiên sinh viên năm nhất, sinh viên vùng xa. Liên hệ: 024.3765.5xxx.',
    },
    'default': 'Cảm ơn bạn đã liên hệ! Câu hỏi của bạn cần tư vấn viên chuyên môn trả lời. Tôi đã ghi nhận và sẽ thông báo khi có tư vấn viên online. Trong lúc chờ, bạn có thể truy cập https://www.haui.edu.vn để tìm thêm thông tin.'
}

psychology_responses = {
    'greeting': 'Xin chào bạn! Tôi là Bot Tư vấn Tâm lý của HaUI. Bạn hoàn toàn có thể chia sẻ bất cứ điều gì tại đây — mọi thông tin đều được bảo mật. Hãy kể cho tôi nghe bạn đang gặp chuyện gì nhé.',
    'keywords': {
        r'stress|áp lực|ap luc|căng thẳng|cang thang|mệt mỏi|met moi': 'Tôi hiểu cảm giác căng thẳng và mệt mỏi rất khó chịu. Đây là một số gợi ý:\n\n1. 🧘 Thử hít thở sâu 4-7-8: hít vào 4 giây, giữ 7 giây, thở ra 8 giây\n2. 🚶 Đi bộ nhẹ 15-20 phút\n3. 📝 Viết ra 3 điều tích cực trong ngày\n4. 💤 Đảm bảo ngủ đủ 7-8 tiếng\n\nNếu tình trạng kéo dài, hãy đợi tư vấn viên chuyên nghiệp nhé!',
        r'lo âu|lo au|lo lắng|lo lang|sợ|so|hoang mang|bất an|bat an': 'Lo âu là cảm xúc rất bình thường. Bạn không cô đơn trong cảm giác này đâu. Hãy thử:\n\n• Xác định cụ thể điều gì khiến bạn lo?\n• Tự hỏi: "Điều tệ nhất có thể xảy ra là gì? Tôi sẽ xử lý thế nào?"\n• Tập trung vào hiện tại, không nghĩ quá xa\n\nTư vấn viên sẽ hỗ trợ bạn kỹ hơn khi online.',
        r'buồn|buon|chán|chan|cô đơn|co don|trống rỗng|trong rong|khóc|khoc': 'Cảm ơn bạn đã tin tưởng chia sẻ. Cảm giác buồn bã là hoàn toàn hợp lệ — bạn không cần phải giấu đi. Một vài điều có thể giúp:\n\n🌟 Kết nối với ai đó: bạn bè, gia đình\n🎵 Nghe nhạc bạn thích\n🌿 Ra ngoài đón ánh nắng\n📖 Làm điều gì đó nhỏ bé khiến bạn vui\n\nNhớ rằng: mưa rồi sẽ tạnh. ❤️',
        r'thi|điểm|diem|trượt|truot|rớt|rot|học kém|hoc kem|thi lại|thi lai': 'Áp lực về điểm số là rất phổ biến. Hãy nhớ rằng điểm số không định nghĩa giá trị của bạn!\n\n💡 Thử lập kế hoạch học tập cụ thể\n📚 Chia nhỏ bài vở thành từng phần\n👥 Tìm nhóm học cùng bạn bè\n⏰ Đặt thời gian nghỉ giữa các buổi học\n\nTư vấn viên có thể giúp bạn xây dựng lộ trình phù hợp hơn!',
        r'bạn bè|ban be|mối quan hệ|moi quan he|bạn trai|ban trai|bạn gái|ban gai|tình yêu|tinh yeu|chia tay': 'Mối quan hệ là phần quan trọng trong cuộc sống. Khi gặp khó khăn trong quan hệ:\n\n💬 Giao tiếp thẳng thắn và lắng nghe\n🤝 Tôn trọng ranh giới của nhau\n💪 Nhớ rằng bạn xứng đáng được đối xử tốt\n\nĐây là vấn đề cần tư vấn viên chuyên môn hỗ trợ. Bạn đợi một chút nhé!',
        r'gia đình|gia dinh|bố mẹ|bo me|anh chị|anh chi|áp lực gia đình|ap luc gia dinh': 'Mối quan hệ gia đình đôi khi rất phức tạp. Bạn hoàn toàn có quyền có cảm xúc riêng. Hãy thử:\n\n❤️ Tìm thời điểm phù hợp để nói chuyện\n📝 Viết ra cảm xúc trước khi trao đổi\n🤗 Tìm người lớn tin tưởng để tâm sự\n\nTư vấn viên tâm lý sẽ giúp bạn tìm cách giải quyết phù hợp nhất.',
        r'nghề nghiệp|nghe nghiep|tương lai|tuong lai|ra trường|ra truong|việc làm|viec lam|định hướng|dinh huong': 'Băn khoăn về tương lai là hoàn toàn bình thường ở tuổi sinh viên!\n\n🎯 Khám phá thế mạnh & sở thích của bạn\n📋 Thử tham gia CLB, hoạt động ngoại khóa\n🏢 Tìm kiếm cơ hội thực tập\n💻 Tham khảo: Trung tâm Hỗ trợ Sinh viên HaUI\n\nTư vấn viên có thể giúp bạn làm rõ hướng đi!',
        r'tự tử|tu tu|chết|chet|không muốn sống|khong muon song|tự hại|tu hai|cắt tay|cat tay': 'Tôi rất lo lắng cho bạn. Bạn rất dũng cảm khi chia sẻ điều này.\n\n🆘 Nếu bạn đang trong tình trạng nguy hiểm, xin hãy gọi NGAY:\n📞 Đường dây nóng tâm lý: 1800 599 920 (miễn phí)\n📞 Cấp cứu: 115\n\nBạn KHÔNG một mình. Có người sẵn sàng giúp bạn. Tư vấn viên chuyên nghiệp sẽ kết nối với bạn sớm nhất có thể. ❤️',
    },
    'default': 'Cảm ơn bạn đã chia sẻ. Tôi đã ghi nhận và tư vấn viên tâm lý chuyên nghiệp sẽ được thông báo. Trong khi chờ, hãy nhớ rằng: bạn đang làm rất tốt khi chọn tìm kiếm sự hỗ trợ. 💚'
}


def get_bot_response(message, branch):
    """Get automated bot response based on message content and branch"""
    responses = academic_responses if branch == 'academic' else psychology_responses
    message_lower = message.lower()

    for pattern, response in responses['keywords'].items():
        if re.search(pattern, message_lower):
            return response

    return responses['default']


# ===================== ROUTES =====================

@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('public', path)


# ===================== SOCKET EVENTS =====================

@socketio.on('connect')
def handle_connect():
    print(f'[+] Client connected: {request.sid if hasattr(request, "sid") else "unknown"}')

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid

    # If student disconnects
    if sid in sid_to_session:
        session_id = sid_to_session[sid]
        session = sessions.get(session_id)
        if session:
            session['socketSid'] = None
            counselor_sid = session.get('counselorSid')
            if counselor_sid and counselor_sid in counselors:
                emit('student:offline', {'sessionId': session_id}, to=counselor_sid)
        del sid_to_session[sid]
        broadcast_queue()
        print(f'[-] Socket disconnected: {sid} (Session: {session_id[:8]}...)')

    # If counselor disconnects (refresh/close)
    if sid in counselors:
        c_name = counselors[sid].get('name')
        # We DON'T revert to waiting immediately to allow for refresh/reconnect
        for s_id, session in sessions.items():
            if session.get('counselorSid') == sid:
                session['counselorSid'] = None
                # Keep status as 'chatting' so counselor can resume
                # If they don't reconnect in a real app, we'd have a timeout here
        del counselors[sid]
        broadcast_queue()
        print(f'[-] Counselor disconnected: {sid} ({c_name})')


# ---- Student Events ----

@socketio.on('student:join')
def handle_student_join(data):
    sid = request.sid
    session_id = data.get('sessionId')

    if not session_id:
        return

    # Check if session exists (reconnection)
    is_new = session_id not in sessions
    if is_new:
        sessions[session_id] = {
            'sessionId': session_id,
            'socketSid': sid,
            'name': data.get('name', 'Ẩn danh'),
            'studentId': data.get('studentId', 'N/A'),
            'className': data.get('className', 'N/A'),
            'issue': data.get('issue', ''),
            'branch': data.get('branch', 'academic'),
            'status': 'waiting',
            'counselorSid': None,
            'joinedAt': time.time(),
            'messages': []
        }
    else:
        # Update socket for old session
        sessions[session_id]['socketSid'] = sid
        # Sync basic info if provided (optional)
        if data.get('name'): sessions[session_id]['name'] = data['name']
        if data.get('branch'): sessions[session_id]['branch'] = data['branch']

    sid_to_session[sid] = session_id
    session = sessions[session_id]

    # Status & Queue
    waiting = [s for s in sessions.values() if s['status'] == 'waiting']
    emit('student:queued', {
        'position': len(waiting),
        'history': session['messages'],
        'status': session['status'],
        'counselorName': counselors.get(session['counselorSid'], {}).get('name') if session['counselorSid'] else None
    })

    # Notify counselor of reconnection if chatting
    if session['counselorSid'] and session['counselorSid'] in counselors:
        emit('student:online', {'sessionId': session_id}, to=session['counselorSid'])

    broadcast_queue()

    # Schedule bot greeting ONLY if it's a new session
    if is_new:
        schedule_bot_greeting(session_id)
        print(f'[+] New Student: {session["name"]} ({session["branch"]})')
    else:
        print(f'[*] Reconnected Student: {session["name"]}')


@socketio.on('student:typing')
def handle_student_typing():
    sid = request.sid
    if sid in sid_to_session:
        session_id = sid_to_session[sid]
        session = sessions[session_id]
        if session.get('counselorSid'):
            emit('student:typing', {'sessionId': session_id}, to=session['counselorSid'])


@socketio.on('student:stopTyping')
def handle_student_stop_typing():
    sid = request.sid
    if sid in sid_to_session:
        session_id = sid_to_session[sid]
        session = sessions[session_id]
        if session.get('counselorSid'):
            emit('student:stopTyping', {'sessionId': session_id}, to=session['counselorSid'])


# ---- Counselor Events ----

@socketio.on('counselor:join')
def handle_counselor_join(data):
    sid = request.sid
    c_name = data.get('name', 'Tư vấn viên')
    counselors[sid] = {'name': c_name}
    
    # RESUME: Re-bind any sessions that were handled by this counselor name
    for s_id, session in sessions.items():
        if session.get('counselorName') == c_name and session.get('counselorSid') is None:
            session['counselorSid'] = sid
            print(f'[+] Counselor {c_name} resumed session: {session["name"]}')

    broadcast_queue()
    print(f'[+] Counselor joined: {c_name}')


@socketio.on('counselor:accept')
def handle_counselor_accept(data):
    sid = request.sid
    session_id = data.get('sessionId')

    if session_id in sessions:
        session = sessions[session_id]
        counselor_name = counselors.get(sid, {}).get('name', 'Tư vấn viên')
        
        session['status'] = 'chatting'
        session['counselorSid'] = sid
        session['counselorName'] = counselor_name # Store name for resume logic

        counselor_name = counselors.get(sid, {}).get('name', 'Tư vấn viên')

        # Notify student if online
        if session['socketSid']:
            emit('counselor:connected', {'counselorName': counselor_name}, to=session['socketSid'])

        broadcast_queue()
        print(f'[✓] Counselor accepted session: {session["name"]}')


@socketio.on('counselor:typing')
def handle_counselor_typing(data):
    session_id = data.get('sessionId')
    if session_id in sessions:
        target_sid = sessions[session_id]['socketSid']
        if target_sid:
            emit('counselor:typing', {}, to=target_sid)


@socketio.on('counselor:stopTyping')
def handle_counselor_stop_typing(data):
    session_id = data.get('sessionId')
    if session_id in sessions:
        target_sid = sessions[session_id]['socketSid']
        if target_sid:
            emit('counselor:stopTyping', {}, to=target_sid)


# ---- Chat Events ----

@socketio.on('chat:message')
def handle_chat_message(data):
    sid = request.sid
    message = data.get('message', '')

    # Student sending message
    if sid in sid_to_session:
        session_id = sid_to_session[sid]
        session = sessions[session_id]
        
        # Save to history
        msg_obj = {'text': message, 'type': 'sent', 'senderName': session['name'], 'time': time.time()}
        session['messages'].append(msg_obj)

        counselor_sid = session.get('counselorSid')
        if counselor_sid and counselor_sid in counselors:
            emit('chat:message', {
                'sessionId': session_id,
                'message': message,
                'senderName': session['name']
            }, to=counselor_sid)
        else:
            schedule_bot_reply(session_id, message, session.get('branch', 'academic'))

    # Counselor sending message
    elif sid in counselors:
        # sessionId should come from counselor side
        student_session_id = data.get('sessionId')
        if student_session_id and student_session_id in sessions:
            session = sessions[student_session_id]
            counselor_name = counselors[sid]['name']

            # Save to history
            msg_obj = {'text': message, 'type': 'received', 'senderName': counselor_name, 'time': time.time()}
            session['messages'].append(msg_obj)

            if session['socketSid']:
                emit('chat:message', {
                    'message': message,
                    'senderName': counselor_name
                }, to=session['socketSid'])


@socketio.on('chat:end')
def handle_chat_end(data=None):
    sid = request.sid

    # Student ending
    if sid in sid_to_session:
        session_id = sid_to_session[sid]
        session = sessions[session_id]
        counselor_sid = session.get('counselorSid')
        if counselor_sid and counselor_sid in counselors:
            emit('chat:ended', {'sessionId': session_id}, to=counselor_sid)
        del sessions[session_id]
        # Cleanup mapping might happen naturally on disconnect, but let's be safe
        broadcast_queue()

    # Counselor ending
    elif sid in counselors and data:
        session_id = data.get('sessionId')
        if session_id and session_id in sessions:
            session = sessions[session_id]
            if session['socketSid']:
                emit('chat:ended', {'message': 'Tư vấn viên đã kết thúc cuộc trò chuyện. Cảm ơn bạn đã sử dụng dịch vụ!'}, to=session['socketSid'])
            del sessions[session_id]
            broadcast_queue()


# ===================== HELPERS =====================

def broadcast_queue():
    """Send updated queue to all counselors"""
    queue = [
        {
            'id': sid,  # sessionId
            'name': s['name'],
            'studentId': s['studentId'],
            'className': s['className'],
            'issue': s['issue'],
            'branch': s['branch'],
            'status': s['status'],
            'isOnline': s['socketSid'] is not None,
            'messages': s['messages'] # HISTORY FOR ADMIN
        }
        for sid, s in sessions.items()
    ]
    for c_sid in counselors:
        socketio.emit('queue:update', queue, to=c_sid)


def schedule_bot_greeting(session_id):
    """Send bot greeting after a short delay"""
    def send_greeting():
        socketio.sleep(1.5)
        if session_id in sessions:
            session = sessions[session_id]
            branch = session.get('branch', 'academic')
            responses = academic_responses if branch == 'academic' else psychology_responses
            
            # Save bot message to history
            msg_obj = {'text': responses['greeting'], 'type': 'received', 'senderName': 'Bot', 'time': time.time()}
            session['messages'].append(msg_obj)

            if session['socketSid']:
                socketio.emit('bot:message', {'message': responses['greeting']}, to=session['socketSid'])

            # If no counselor after BOT_DELAY, send follow-up
            def check_counselor():
                socketio.sleep(BOT_DELAY)
                if session_id in sessions:
                    current_session = sessions[session_id]
                    if not current_session.get('counselorSid'):
                        msg = 'Hiện tại chưa có tư vấn viên online. Tôi sẽ cố gắng giải đáp cho bạn. Hãy hỏi tôi bất cứ điều gì!'
                        # Save follow-up to history
                        f_msg = {'text': msg, 'type': 'received', 'senderName': 'Bot', 'time': time.time()}
                        current_session['messages'].append(f_msg)
                        
                        if current_session['socketSid']:
                            socketio.emit('bot:message', {'message': msg}, to=current_session['socketSid'])

            socketio.start_background_task(check_counselor)

    socketio.start_background_task(send_greeting)


def schedule_bot_reply(session_id, message, branch):
    """Schedule bot auto-reply when no counselor is available"""
    def send_reply():
        socketio.sleep(1.5)
        if session_id in sessions:
            session = sessions[session_id]
            if not session.get('counselorSid'):
                response = get_bot_response(message, branch)
                
                # Save bot reply to history
                msg_obj = {'text': response, 'type': 'received', 'senderName': 'Bot', 'time': time.time()}
                session['messages'].append(msg_obj)
                
                if session['socketSid']:
                    socketio.emit('bot:message', {'message': response}, to=session['socketSid'])

    socketio.start_background_task(send_reply)


def schedule_bot(session_id):
    """Re-enable bot for a student who lost their counselor"""
    def send_msg():
        socketio.sleep(2)
        if session_id in sessions:
            session = sessions[session_id]
            if not session.get('counselorSid'):
                text = 'Tư vấn viên đã ngắt kết nối. Bot sẽ tiếp tục hỗ trợ bạn trong khi chờ tư vấn viên khác.'
                msg_obj = {'text': text, 'type': 'received', 'senderName': 'Bot', 'time': time.time()}
                session['messages'].append(msg_obj)
                
                if session['socketSid']:
                    socketio.emit('bot:message', {'message': text}, to=session['socketSid'])

    socketio.start_background_task(send_msg)


# ===================== MAIN =====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n  HaUI Counseling Chat Server")
    print(f"  -> http://localhost:{port}")
    print(f"  -> Admin: http://localhost:{port}/admin.html")
    print(f"  -> Login: admin / haui2026\n")
    socketio.run(app, host='0.0.0.0', port=port, debug=True, allow_unsafe_werkzeug=True)
