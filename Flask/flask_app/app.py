from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
import os

app = Flask(__name__, instance_relative_config=True)

# Make sure the instance folder exists
try:
    os.makedirs(app.instance_path)
except OSError:
    pass

# Configure SQLAlchemy to use the instance folder
db_path = os.path.join(app.instance_path, 'database.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['DEBUG'] = True

# Enable CORS for all domains in development
CORS(app, resources={r"/api/*": {"origins": "*"}})

db = SQLAlchemy(app)

class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@app.route('/api/contact', methods=['POST'])
def contact():
    try:
        print("Received contact form submission")  # Debug print
        data = request.get_json()
        print(f"Request data: {data}")  # Debug print
        
        if not all([data.get('name'), data.get('email'), data.get('message')]):
            print("Missing required fields")  # Debug print
            return jsonify({'message': 'Name, email and message are required'}), 400
            
        contact = Contact(
            name=data['name'],
            email=data['email'],
            subject=data.get('subject', 'No Subject'),
            message=data['message']
        )
        
        db.session.add(contact)
        db.session.commit()
        print(f"Successfully saved contact: {contact.id}")  # Debug print
            
        return jsonify({'message': 'Message sent successfully'}), 201
    except Exception as e:
        db.session.rollback()
        print(f"Error processing contact form: {str(e)}")
        return jsonify({'message': f'An error occurred processing your request: {str(e)}'}), 500

if __name__ == '__main__':
    with app.app_context():
        # Create the database and tables if they don't exist
        if not os.path.exists(db_path):
            db.create_all()
            print(f"Database initialized successfully at {db_path}")
        else:
            print(f"Using existing database at {db_path}")
    
    app.run(debug=True, port=5000)