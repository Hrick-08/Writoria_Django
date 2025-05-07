from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import django
import os
import sys

django_project_path = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'Django'))
sys.path.append(django_project_path)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'writoria.settings')
django.setup()

from django.contrib.auth.models import User as DjangoUser
from django.db import IntegrityError

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = 'super-secret-key'  
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = 3600
app.config['JWT_TOKEN_LOCATION'] = ['headers']
app.config['JWT_HEADER_NAME'] = 'Authorization'
app.config['JWT_HEADER_TYPE'] = 'Bearer'
db = SQLAlchemy(app)
jwt = JWTManager(app)
CORS(app, resources={r"/api/*": {"origins": ["http://localhost:8000", "http://127.0.0.1:8000", "*"]}})  

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    bio = db.Column(db.Text, nullable=True)
    profile_pic = db.Column(db.String(200), nullable=True)

class Blog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    author = db.relationship('User', backref=db.backref('blogs', lazy=True))

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    blog_id = db.Column(db.Integer, db.ForeignKey('blog.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('comments', lazy=True))
    blog = db.relationship('Blog', backref=db.backref('comments', lazy=True))

# JWT Error Handlers
@jwt.unauthorized_loader
def unauthorized_response(error_string):
    return jsonify({'message': error_string}), 401

@jwt.invalid_token_loader
def invalid_token_response(error_string):
    return jsonify({'message': error_string}), 422

@jwt.expired_token_loader
def expired_token_response(jwt_header, jwt_data):
    return jsonify({'message': 'Token has expired'}), 401

# User Routes
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'message': 'Username and password required'}), 400
        
    # Check if user exists in Flask DB
    if User.query.filter_by(username=username).first():
        return jsonify({'message': 'Username already exists'}), 400
        
    try:
        # Create user in Django DB
        django_user = DjangoUser.objects.create_user(username=username, password=password)
        
        # Create user in Flask DB
        flask_user = User(
            username=username,
            password=generate_password_hash(password)
        )
        db.session.add(flask_user)
        db.session.commit()
        
        return jsonify({'message': 'User registered successfully'}), 201
        
    except IntegrityError:
        db.session.rollback()
        return jsonify({'message': 'Username already exists in Django database'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': f'Registration failed: {str(e)}'}), 500

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({'message': 'No data provided'}), 400
        
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'message': 'Username and password are required'}), 400
        
    # Check Flask database
    flask_user = User.query.filter_by(username=username).first()
    
    # Check Django database
    try:
        django_user = DjangoUser.objects.get(username=username)
        if not django_user.check_password(password):
            return jsonify({'message': 'Invalid credentials'}), 401
    except DjangoUser.DoesNotExist:
        # If user exists in Flask but not in Django, create in Django
        if flask_user and check_password_hash(flask_user.password, password):
            DjangoUser.objects.create_user(username=username, password=password)
        else:
            return jsonify({'message': 'Invalid credentials'}), 401
    
    if not flask_user:
        # If user exists in Django but not in Flask, create in Flask
        flask_user = User(username=username, password=generate_password_hash(password))
        db.session.add(flask_user)
        db.session.commit()
    elif not check_password_hash(flask_user.password, password):
        return jsonify({'message': 'Invalid credentials'}), 401
    
    # Create JWT token
    access_token = create_access_token(identity=str(flask_user.id))
    return jsonify({
        'access_token': access_token,
        'token_type': 'Bearer',
        'user_id': flask_user.id
    }), 200

@app.route('/api/profile', methods=['GET', 'PUT'])
@jwt_required()
def profile():
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)
    if request.method == 'GET':
        return jsonify({
            'id': user.id,
            'username': user.username,
            'bio': user.bio or "",  # Return empty string instead of null
            'profile_pic': user.profile_pic or "",  # Return empty string instead of null
            'blogs': [{'id': blog.id, 'title': blog.title} for blog in user.blogs]  # Fixed from logs to blogs
        }), 200
    elif request.method == 'PUT':
        data = request.get_json()
        user.bio = data.get('bio', user.bio)
        user.profile_pic = data.get('profile_pic', user.profile_pic)
        db.session.commit()
        return jsonify({'message': 'Profile updated successfully'}), 200

# Blog Routes
@app.route('/api/blogs', methods=['GET', 'POST'])
@jwt_required(optional=True)  # Allow GET without token
def blogs():
    if request.method == 'POST':
        # Ensure user is authenticated for POST
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'message': 'Authentication required'}), 401
            
        # Check if request has JSON content
        if not request.is_json:
            return jsonify({'message': 'Content-Type must be application/json'}), 415
            
        data = request.get_json()
        if not data or not data.get('title') or not data.get('content'):
            return jsonify({'message': 'Title and content are required'}), 400
            
        try:
            # Get the user from Flask DB
            user = User.query.get(int(user_id))
            
            # If user doesn't exist in Flask but exists in Django, create in Flask
            if not user:
                try:
                    django_user = DjangoUser.objects.get(id=int(user_id))
                    user = User(
                        id=django_user.id,
                        username=django_user.username,
                        password='unusable'  # Since auth is handled by Django
                    )
                    db.session.add(user)
                    try:
                        db.session.commit()
                    except Exception as e:
                        db.session.rollback()
                        return jsonify({'message': f'Failed to create user in Flask: {str(e)}'}), 500
                except DjangoUser.DoesNotExist:
                    return jsonify({'message': 'User not found in Django database'}), 404
            
            # Create the blog post
            blog = Blog(
                title=data['title'],
                content=data['content'],
                author_id=user.id,
                author=user
            )
            db.session.add(blog)
            
            try:
                db.session.commit()
                return jsonify({
                    'status': 'success',
                    'message': 'Blog created successfully',
                    'blog': {
                        'id': blog.id,
                        'title': blog.title,
                        'content': blog.content,
                        'timestamp': blog.timestamp.isoformat(),
                        'author': user.username
                    }
                }), 201
            except Exception as e:
                db.session.rollback()
                return jsonify({'message': f'Failed to create blog: {str(e)}'}), 500
                
        except Exception as e:
            return jsonify({'message': f'Server error: {str(e)}'}), 500
    
    # GET method
    blogs = Blog.query.all()
    return jsonify([{
        'id': b.id,
        'title': b.title,
        'content': b.content,
        'timestamp': b.timestamp.isoformat(),
        'author': b.author.username if b.author else None
    } for b in blogs])

@app.route('/api/blogs/<int:id>', methods=['GET', 'DELETE'])
@jwt_required()
def get_blog(id):
    blog = Blog.query.get_or_404(id)
    
    if request.method == 'DELETE':
        # Get the current user's ID from the JWT token
        current_user_id = get_jwt_identity()
        
        try:
            # Get the user from Flask DB
            user = User.query.get(int(current_user_id))
            if not user:
                # If user doesn't exist in Flask but exists in Django, create in Flask
                try:
                    django_user = DjangoUser.objects.get(id=int(current_user_id))
                    user = User(
                        id=django_user.id,
                        username=django_user.username,
                        password='unusable'  # Since auth is handled by Django
                    )
                    db.session.add(user)
                    try:
                        db.session.commit()
                    except Exception as e:
                        db.session.rollback()
                        return jsonify({'message': f'Failed to create user in Flask: {str(e)}'}), 500
                except DjangoUser.DoesNotExist:
                    return jsonify({'message': 'User not found in Django database'}), 404
            
            # Check if user owns the blog
            if blog.author_id != user.id:
                return jsonify({'message': 'Unauthorized - you do not own this blog post'}), 403
                
            try:
                # First delete all comments associated with this blog
                Comment.query.filter_by(blog_id=id).delete()
                # Then delete the blog
                db.session.delete(blog)
                db.session.commit()
                return jsonify({'message': 'Blog deleted successfully'}), 200
            except Exception as e:
                db.session.rollback()
                return jsonify({'message': f'Failed to delete blog: {str(e)}'}), 500
                
        except Exception as e:
            return jsonify({'message': f'Server error: {str(e)}'}), 500
    
    # GET method
    return jsonify({
        'id': blog.id,
        'title': blog.title,
        'content': blog.content,
        'timestamp': blog.timestamp.isoformat(),
        'author': blog.author.username
    })

# Comment Routes
@app.route('/api/blogs/<int:blog_id>/comments', methods=['GET', 'POST'])
@jwt_required(optional=True)  # Allow GET without token, require token for POST
def comments(blog_id):
    if request.method == 'GET':
        comments = Comment.query.filter_by(blog_id=blog_id).all()
        return jsonify([{
            'id': c.id,
            'content': c.content,
            'timestamp': c.timestamp.isoformat(),
            'username': c.user.username
        } for c in comments])
    elif request.method == 'POST':
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'message': 'Authentication required'}), 401
            
        # Check if request has JSON content
        if not request.is_json:
            return jsonify({'message': 'Content-Type must be application/json'}), 415
            
        data = request.get_json()
        if not data or not data.get('content'):
            return jsonify({'message': 'Comment content is required'}), 400
            
        # Verify blog exists
        blog = Blog.query.get_or_404(blog_id)
        
        comment = Comment(
            content=data.get('content'),
            user_id=int(user_id),
            blog_id=blog_id
        )
        db.session.add(comment)
        try:
            db.session.commit()
            return jsonify({
                'status': 'success',
                'message': 'Comment added successfully',
                'comment': {
                    'id': comment.id,
                    'content': comment.content,
                    'timestamp': comment.timestamp.isoformat(),
                    'username': comment.user.username
                }
            }), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({'message': f'Failed to add comment: {str(e)}'}), 500

@app.route('/api/blogs/comments/<int:comment_id>', methods=['DELETE'])
@jwt_required()
def delete_comment(comment_id):
    user_id = int(get_jwt_identity())
    comment = Comment.query.get_or_404(comment_id)
    
    # Check if user owns the comment
    if comment.user_id != user_id:
        return jsonify({'message': 'Unauthorized'}), 403
        
    try:
        db.session.delete(comment)
        db.session.commit()
        return jsonify({'message': 'Comment deleted successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': 'Failed to delete comment: ' + str(e)}), 500

# Chatbot Route (Mock)
@app.route('/api/chatbot', methods=['POST'])
def chatbot():
    data = request.get_json()
    user_message = data.get('message')
    # Mock chatbot response (replace with Ollama integration in production)
    mock_response = f"Bot: I understood your message: '{user_message}'. How can I assist you further?"
    return jsonify({'response': mock_response}), 200

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)