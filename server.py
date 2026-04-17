"""
HaUI Counseling Chat Server
Flask + Socket.IO real-time chat with Auth
"""

from flask import Flask, send_from_directory, request, jsonify, url_for, redirect
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os, time, threading, re, uuid

app = Flask(__name__, static_folder='public', static_url_path='')
app.config['SECRET_KEY'] = 'haui-secret-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'public/uploads'

# Ensure upload directory exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# ===================== MODELS =====================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    student_id = db.Column(db.String(20))
    class_name = db.Column(db.String(50))
    avatar_url = db.Column(db.String(255), default='/images/haui-logo.png')
    role = db.Column(db.String(20), default='student') # 'student' or 'counselor'

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# ===================== AUTH SETUP =====================

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_page'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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


# ===================== AUTH ROUTES =====================

@app.route('/login')
def login_page():
    return send_from_directory('public', 'login.html')

@app.route('/register')
def register_page():
    return send_from_directory('public', 'register.html')

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.json
    if User.query.filter_by(email=data.get('email')).first():
        return jsonify({'error': 'Email đã tồn tại'}), 400
    
    user = User(
        email=data.get('email'),
        name=data.get('name'),
        student_id=data.get('studentId'),
        class_name=data.get('className')
    )
    user.set_password(data.get('password'))
    db.session.add(user)
    db.session.commit()
    return jsonify({'message': 'Đăng ký thành công!'})

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    user = User.query.filter_by(email=data.get('email')).first()
    if user and user.check_password(data.get('password')):
        login_user(user, remember=True)
        return jsonify({'message': 'Đăng nhập thành công', 'user': {
            'name': user.name,
            'avatarUrl': user.avatar_url
        }})
    return jsonify({'error': 'Email hoặc mật khẩu không chính xác'}), 401

@app.route('/api/logout')
@login_required
def api_logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/api/profile', methods=['GET'])
@login_required
def get_profile():
    return jsonify({
        'name': current_user.name,
        'email': current_user.email,
        'studentId': current_user.student_id,
        'className': current_user.class_name,
        'avatarUrl': current_user.avatar_url
    })

@app.route('/api/profile/update', methods=['POST'])
@login_required
def update_profile():
    data = request.json
    current_user.name = data.get('name', current_user.name)
    current_user.student_id = data.get('studentId', current_user.student_id)
    current_user.class_name = data.get('className', current_user.class_name)
    db.session.commit()
    return jsonify({'message': 'Cập nhật thành công'})

@app.route('/api/profile/upload-avatar', methods=['POST'])
@login_required
def upload_avatar():
    if 'avatar' not in request.files:
        return jsonify({'error': 'Không có tệp tin'}), 400
    
    file = request.files['avatar']
    if file.filename == '':
        return jsonify({'error': 'Chưa chọn tệp tin'}), 400

    filename = secure_filename(f"user_{current_user.id}_{int(time.time())}_{file.filename}")
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)
    
    current_user.avatar_url = f"/uploads/{filename}"
    db.session.commit()
    
    return jsonify({'avatarUrl': current_user.avatar_url})


# ===================== CORE ROUTES =====================

@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

@app.route('/profile')
@login_required
def profile_page():
    return send_from_directory('public', 'profile.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('public', path)


# ===================== SOCKET EVENTS =====================

@socketio.on('connect')
def handle_connect():
    print(f'[+] Client connected: {request.sid}')

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
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
    if sid in counselors:
        del counselors[sid]
        broadcast_queue()

# ---- Student Events ----

@socketio.on('student:join')
def handle_student_join(data):
    sid = request.sid
    # If user is logged in, use their info
    if current_user.is_authenticated:
        session_id = f"user_{current_user.id}"
        name = current_user.name
        student_id = current_user.student_id
        class_name = current_user.class_name
        avatar_url = current_user.avatar_url
    else:
        session_id = data.get('sessionId', str(uuid.uuid4()))
        name = data.get('name', 'Ẩn danh')
        student_id = data.get('studentId', 'N/A')
        class_name = data.get('className', 'N/A')
        avatar_url = '/images/haui-logo.png'

    if session_id not in sessions:
        sessions[session_id] = {
            'sessionId': session_id,
            'socketSid': sid,
            'name': name,
            'studentId': student_id,
            'className': class_name,
            'avatarUrl': avatar_url,
            'issue': data.get('issue', ''),
            'branch': data.get('branch', 'academic'),
            'status': 'waiting',
            'counselorSid': None,
            'joinedAt': time.time(),
            'messages': []
        }
    else:
        sessions[session_id]['socketSid'] = sid

    sid_to_session[sid] = session_id
    session = sessions[session_id]

    waiting = [s for s in sessions.values() if s['status'] == 'waiting']
    emit('student:queued', {
        'position': len(waiting),
        'history': session['messages'],
        'status': session['status'],
        'counselorName': counselors.get(session['counselorSid'], {}).get('name') if session['counselorSid'] else None
    })

    if session['counselorSid'] and session['counselorSid'] in counselors:
        emit('student:online', {'sessionId': session_id}, to=session['counselorSid'])

    broadcast_queue()
    if len(session['messages']) == 0:
        schedule_bot_greeting(session_id)

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
    broadcast_queue()

@socketio.on('counselor:accept')
def handle_counselor_accept(data):
    sid = request.sid
    session_id = data.get('sessionId')
    if session_id in sessions:
        session = sessions[session_id]
        counselor_name = counselors.get(sid, {}).get('name', 'Tư vấn viên')
        session['status'] = 'chatting'
        session['counselorSid'] = sid
        session['counselorName'] = counselor_name
        if session['socketSid']:
            emit('counselor:connected', {'counselorName': counselor_name}, to=session['socketSid'])
        broadcast_queue()

# ---- Chat Events ----

@socketio.on('chat:message')
def handle_chat_message(data):
    sid = request.sid
    message = data.get('message', '')
    if sid in sid_to_session:
        session_id = sid_to_session[sid]
        session = sessions[session_id]
        msg_obj = {'text': message, 'type': 'sent', 'senderName': session['name'], 'time': time.time(), 'avatarUrl': session.get('avatarUrl')}
        session['messages'].append(msg_obj)
        counselor_sid = session.get('counselorSid')
        if counselor_sid and counselor_sid in counselors:
            emit('chat:message', {
                'sessionId': session_id,
                'message': message,
                'senderName': session['name'],
                'avatarUrl': session.get('avatarUrl')
            }, to=counselor_sid)
        else:
            schedule_bot_reply(session_id, message, session.get('branch', 'academic'))
    elif sid in counselors:
        student_session_id = data.get('sessionId')
        if student_session_id and student_session_id in sessions:
            session = sessions[student_session_id]
            counselor_name = counselors[sid]['name']
            msg_obj = {'text': message, 'type': 'received', 'senderName': counselor_name, 'time': time.time()}
            session['messages'].append(msg_obj)
            if session['socketSid']:
                emit('chat:message', {'message': message, 'senderName': counselor_name}, to=session['socketSid'])

# ===================== HELPERS =====================

def broadcast_queue():
    queue = [
        {
            'id': sid,
            'name': s['name'],
            'studentId': s['studentId'],
            'className': s['className'],
            'branch': s['branch'],
            'status': s['status'],
            'isOnline': s['socketSid'] is not None,
            'messages': s['messages'],
            'avatarUrl': s.get('avatarUrl')
        }
        for sid, s in sessions.items()
    ]
    for c_sid in counselors:
        socketio.emit('queue:update', queue, to=c_sid)

def schedule_bot_greeting(session_id):
    def send_greeting():
        socketio.sleep(1.5)
        if session_id in sessions:
            session = sessions[session_id]
            branch = session.get('branch', 'academic')
            responses = academic_responses if branch == 'academic' else psychology_responses
            msg_obj = {'text': responses['greeting'], 'type': 'received', 'senderName': 'Bot', 'time': time.time()}
            session['messages'].append(msg_obj)
            if session['socketSid']:
                socketio.emit('bot:message', {'message': responses['greeting']}, to=session['socketSid'])
    socketio.start_background_task(send_greeting)

def schedule_bot_reply(session_id, message, branch):
    def send_reply():
        socketio.sleep(1.5)
        if session_id in sessions:
            session = sessions[session_id]
            if not session.get('counselorSid'):
                response = get_bot_response(message, branch)
                msg_obj = {'text': response, 'type': 'received', 'senderName': 'Bot', 'time': time.time()}
                session['messages'].append(msg_obj)
                if session['socketSid']:
                    socketio.emit('bot:message', {'message': response}, to=session['socketSid'])
    socketio.start_background_task(send_reply)

# ===================== MAIN =====================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True, allow_unsafe_werkzeug=True)
