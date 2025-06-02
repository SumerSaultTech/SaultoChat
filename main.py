import os
import logging
import uuid
import time
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for, render_template, Response
from flask_cors import CORS
from flask_pymongo import PyMongo
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from openai import AzureOpenAI
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from bson.objectid import ObjectId
import secrets
import urllib.parse
import json
from flask_session import Session

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
app = Flask(__name__, static_folder='static/react-build', static_url_path='')

# Basic Flask Configuration
CORS(app)
app.secret_key = os.environ.get("SESSION_SECRET", "sumersault-dev-secret")

# Session configuration for OAuth state management
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_KEY_PREFIX'] = 'sumersault:'
app.config['PERMANENT_SESSION_LIFETIME'] = 300  # 5 minutes

# Initialize Flask-Session
Session(app)

# OAuth configuration to handle CSRF and state
app.config['AUTHLIB_INSECURE_TRANSPORT'] = True  # Only for development
app.config['PREFERRED_URL_SCHEME'] = 'http'  # Changed to http for local development

# MongoDB Configuration
app.config["MONGO_URI"] = os.environ.get("MONGO_URI", "mongodb://localhost:27017/sumersault")

try:
    mongo = PyMongo(app)
    logger.info(f"PyMongo initialized with URI: {app.config['MONGO_URI']}")

    # Test connection with a simpler approach
    try:
        # Use a simpler connection test
        client = mongo.cx  # Get the underlying pymongo client
        client.admin.command('ping')
        logger.info("✅ MongoDB Atlas connected successfully!")

        # Test database access
        db = client.get_database('SaultoChat')
        logger.info(f"✅ Database 'SaultoChat' accessible")

    except Exception as e:
        logger.error(f"❌ MongoDB connection test failed: {str(e)}")

except Exception as e:
    logger.error(f"❌ PyMongo initialization failed: {str(e)}")
    mongo = None

# Login Manager Setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# OAuth Setup - Microsoft Only (ONLY ONE REGISTRATION)
oauth = OAuth(app)


# File upload configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'csv', 'json', 'zip', 
                     'py', 'js', 'html', 'css', 'c', 'cpp', 'h', 'java', 'rb', 'php', 'xml', 'md'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Initialize OpenAI client
try:
    client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_KEY"),
        api_version="2024-12-01-preview",
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
    )
    logger.info("Azure OpenAI client initialized successfully")
except Exception as e:
    logger.error(f"Error initializing Azure OpenAI client: {str(e)}")
    client = None

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data['_id'])
        self.email = user_data['email']
        self.name = user_data.get('name', '')
        self.company = self._extract_company_from_email(user_data['email'])
        self.job_title = user_data.get('job_title', '')
        self.department = user_data.get('department', '')
        self.role = user_data.get('role', 'user')
        self.microsoft_id = user_data.get('microsoft_id', '')
    
    def get_id(self):
        return self.id
    
    def _extract_company_from_email(self, email):
        """Extract company name from email domain"""
        if not email or '@' not in email:
            return ''
    
        domain = email.split('@')[1]
        # Remove common email providers that don't represent companies
        common_providers = ['gmail.com', 'outlook.com', 'hotmail.com', 'yahoo.com', 'aol.com', 'icloud.com']
        if domain in common_providers:
            return ''
    
        # Otherwise, use the domain as company name
        company_name = domain.split('.')[0].capitalize()
        return company_name
    
@login_manager.user_loader
def load_user(user_id):
    user_data = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    if not user_data:
        return None
    return User(user_data)

# Authentication routes
@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/microsoft-login')  
def microsoft_login():
    import secrets
    import urllib.parse

    # Generate and store state for CSRF protection
    state = secrets.token_urlsafe(32)
    session['oauth_state'] = state
    session.permanent = True  # Make session persistent
    
    # Build authorization URL manually
    redirect_uri = url_for('microsoft_auth', _external=True)
    # Ensure we're using http and localhost
    redirect_uri = redirect_uri.replace('https://', 'http://')
    redirect_uri = redirect_uri.replace('10.40.178.72', 'localhost')

    auth_params = {
        'client_id': os.getenv("MICROSOFT_CLIENT_ID"),
        'response_type': 'code',
        'redirect_uri': redirect_uri,
        'scope': 'openid email profile User.Read',
        'state': state,
        'response_mode': 'query'
    }

    auth_url = 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?' + urllib.parse.urlencode(auth_params)

    logger.info(f"DEBUG: Redirect URI being sent: {redirect_uri}")
    logger.info(f"DEBUG: State generated: {state}")
    logger.info(f"DEBUG: Session state stored: {session.get('oauth_state')}")

    return redirect(auth_url)

@app.route('/microsoft-auth')
def microsoft_auth():
    try:
        import requests

        # Verify state to prevent CSRF
        received_state = request.args.get('state')
        stored_state = session.get('oauth_state')

        logger.info(f"DEBUG: Received state: {received_state}")
        logger.info(f"DEBUG: Stored state: {stored_state}")
        logger.info(f"DEBUG: Session contents: {dict(session)}")

        if not received_state or not stored_state or received_state != stored_state:
            logger.error("State mismatch - CSRF protection triggered")
            logger.error(f"Received state: {received_state}")
            logger.error(f"Stored state: {stored_state}")
            return "Authentication failed: Invalid state", 400

        # Clear the state from session
        session.pop('oauth_state', None)

        # Get authorization code
        code = request.args.get('code')
        error = request.args.get('error')

        if error:
            logger.error(f"OAuth error: {error}")
            return f"Authentication failed: {error}", 400

        if not code:
            logger.error("No authorization code received")
            return "Authentication failed: No authorization code", 400

        # Exchange code for token
        token_url = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'
        redirect_uri = url_for('microsoft_auth', _external=True)
        redirect_uri = redirect_uri.replace('https://', 'http://')
        redirect_uri = redirect_uri.replace('10.40.178.72', 'localhost')

        token_data = {
            'client_id': os.getenv("MICROSOFT_CLIENT_ID"),
            'client_secret': os.getenv("MICROSOFT_CLIENT_SECRET"),
            'code': code,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code'
        }

        logger.info(f"Token request data: {token_data}")

        token_response = requests.post(token_url, data=token_data)
        token_json = token_response.json()

        if 'error' in token_json:
            logger.error(f"Token error: {token_json['error']}")
            logger.error(f"Token error description: {token_json.get('error_description', 'No description')}")
            return f"Authentication failed: {token_json['error']}", 400

        # Get user info from Microsoft Graph
        graph_url = 'https://graph.microsoft.com/v1.0/me'
        headers = {
            'Authorization': f"Bearer {token_json['access_token']}"
        }

        graph_response = requests.get(graph_url, headers=headers)
        user_info = graph_response.json()

        if 'error' in user_info:
            logger.error(f"Graph API error: {user_info['error']}")
            return f"Authentication failed: {user_info['error']['message']}", 400

        email = user_info.get('mail') or user_info.get('userPrincipalName')
        
        # Check if user is authorized
        authorized_user = mongo.db.authorized_users.find_one({'email': email})
        if not authorized_user:
            logger.error(f"Unauthorized access attempt: {email}")
            return "You are not authorized to access this application. Please contact your administrator.", 403

        # Check if user exists in our database
        user = mongo.db.users.find_one({'email': email})
        
        if not user:
            # Create new user
            user_data = {
                'email': email,
                'name': user_info.get('displayName', ''),
                'microsoft_id': user_info.get('id'),
                'role': 'user'
            }
            result = mongo.db.users.insert_one(user_data)
            user = mongo.db.users.find_one({'_id': result.inserted_id})
        
        # Log in the user
        user_obj = User(user)
        login_user(user_obj)
        
        return redirect(url_for('index'))

    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        return f"Authentication failed: {str(e)}", 500

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# API routes for the React frontend
@app.route('/')
@login_required
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

@app.route('/api/conversation', methods=['GET'])
@login_required
def get_conversation():
    conversation_id = request.args.get('id')

    if conversation_id:
        # Convert string ID to ObjectId
        try:
            conversation = mongo.db.conversations.find_one({
                "_id": ObjectId(conversation_id),
                "user_id": ObjectId(current_user.id)
            })

            if not conversation:
                return jsonify({"error": "Conversation not found"}), 404

            # Convert ObjectId to string for JSON serialization
            conversation['id'] = str(conversation['_id'])
            del conversation['_id']
            
            # Convert user_id to string
            if 'user_id' in conversation:
                conversation['user_id'] = str(conversation['user_id'])
            
            # Convert any nested ObjectIds in messages
            if 'messages' in conversation:
                for message in conversation['messages']:
                    if '_id' in message:
                        message['id'] = str(message['_id'])
                        del message['_id']
                    if 'sender_id' in message:
                        message['sender_id'] = str(message['sender_id'])
                    if 'for_user_id' in message:
                        message['for_user_id'] = str(message['for_user_id'])

            return jsonify(conversation)
        except Exception as e:
            logger.error(f"Error retrieving conversation: {str(e)}")
            return jsonify({"error": "Invalid conversation ID"}), 400
    else:
        # Create a new conversation
        new_conversation = {
            "user_id": ObjectId(current_user.id),
            "title": f"New Conversation",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "messages": []
        }

        conversation_id = mongo.db.conversations.insert_one(new_conversation).inserted_id
        new_conversation['id'] = str(conversation_id)
        new_conversation['user_id'] = str(new_conversation['user_id'])
        del new_conversation['_id']
        return jsonify(new_conversation)

@app.route('/api/message_disabled', methods=['POST'])
@login_required
def add_message_disabled():
    file_info = None
    file_path = None

    # Check if the post request has the file part
    if 'file' in request.files:
        file = request.files['file']
        logger.info(f"File received in request: {file.filename if file else 'None'}")

        if file and file.filename and allowed_file(file.filename):
            # Generate a secure filename with UUID to prevent collisions
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4()}_{filename}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)

            # Save the file
            file.save(file_path)

            # Create file info for storing in the message
            file_info = {
                'name': filename,
                'path': file_path,
                'type': file.content_type,
                'size': os.path.getsize(file_path)
            }
            logger.info(f"File uploaded: {filename} ({file_info['size']} bytes), path: {file_path}, type: {file.content_type}")
        else:
            logger.warning(f"File upload failed validation: filename={file.filename if file else 'None'}, allowed={allowed_file(file.filename) if file and file.filename else False}")

    # Get conversation ID and message text from form data
    conversation_id = request.form.get('conversation_id')
    message_text = request.form.get('message', '')

    if not conversation_id:
        return jsonify({'error': 'Missing conversation ID'}), 400

    # Allow empty message text if a file is attached
    if not message_text and not file_info:
        return jsonify({'error': 'Missing message content (text or file)'}), 400

    try:
        # Verify the conversation belongs to the current user
        conversation = mongo.db.conversations.find_one({
            "_id": ObjectId(conversation_id),
            "user_id": ObjectId(current_user.id)
        })

        if not conversation:
            return jsonify({'error': 'Conversation not found or access denied'}), 404

        # Add user message to the conversation with user metadata
        user_message = {
            'id': str(uuid.uuid4()),
            'text': message_text,
            'sender': 'user',
            'sender_id': str(current_user.id),  # Add sender ID for improved tracking
            'sender_email': current_user.email,  # Associate email for audit logs
            'timestamp': datetime.now().isoformat(),
            'file': file_info
        }

        # Generate AI response
        message_with_file_info = message_text
        if file_info:
            message_with_file_info = f"{message_text}\n[File attached: {file_info['name']}]"

        ai_response_text = generate_ai_response(message_with_file_info, conversation.get('messages', []))

        # Add AI response to the conversation with user context
        ai_message = {
            'id': str(uuid.uuid4()),
            'text': ai_response_text,
            'sender': 'bot',
            'for_user_id': str(current_user.id),  # Track which user this response was generated for
            'timestamp': datetime.now().isoformat()
        }

        # Update the conversation with both messages - ensure user can only modify their own conversations
        mongo.db.conversations.update_one(
            {
                "_id": ObjectId(conversation_id),
                "user_id": ObjectId(current_user.id)  # Critical security check
            },
            {
                "$push": {"messages": {"$each": [user_message, ai_message]}},
                "$set": {
                    "updated_at": datetime.now(),
                    "last_accessed_by": current_user.email,  # Track for audit purposes
                    "access_timestamp": datetime.now()
                }
            }
        )

        # Retrieve the updated conversation - with user verification
        updated_conversation = mongo.db.conversations.find_one({
            "_id": ObjectId(conversation_id),
            "user_id": ObjectId(current_user.id)  # Ensure we only return the user's own conversation
        })
        
        if not updated_conversation:
            return jsonify({'error': 'Conversation not found or access denied'}), 404
            
        # Convert ObjectIds to strings
        updated_conversation['id'] = str(updated_conversation['_id'])
        updated_conversation['user_id'] = str(updated_conversation['user_id'])
        del updated_conversation['_id']
        
        # Convert any nested ObjectIds in messages
        if 'messages' in updated_conversation:
            for message in updated_conversation['messages']:
                if '_id' in message:
                    message['id'] = str(message['_id'])
                    del message['_id']
                if 'sender_id' in message:
                    message['sender_id'] = str(message['sender_id'])
                if 'for_user_id' in message:
                    message['for_user_id'] = str(message['for_user_id'])

        return jsonify({'conversation': updated_conversation, 'message': ai_message})

    except Exception as e:
        logger.error(f"Error adding message: {str(e)}")
        return jsonify({'error': f'Failed to add message: {str(e)}'}), 500

@app.route('/api/conversations', methods=['GET'])
@login_required
def get_all_conversations():
    # Return just the list of conversation IDs and their first message for the sidebar
    conversation_list = []
    user_conversations = mongo.db.conversations.find(
        {"user_id": ObjectId(current_user.id)},
        sort=[("updated_at", -1)]  # Sort by most recently updated
    )

    for conv in user_conversations:
        first_message = ''
        if conv.get('messages') and len(conv.get('messages')) > 0:
            first_message = conv.get('messages')[0].get('text', 'New conversation')
        else:
            first_message = "New conversation"

        conversation_list.append({
            'id': str(conv['_id']),
            'preview': first_message[:50] + ('...' if len(first_message) > 50 else ''),
            'pinned': conv.get('pinned', False)  # Include pinned status, default to False if not set
        })

    return jsonify(conversation_list)

@app.route('/api/conversation', methods=['DELETE'])
@login_required
def delete_conversation():
    conversation_id = request.args.get('id')

    if not conversation_id:
        return jsonify({'error': 'Missing conversation ID'}), 400

    try:
        # Verify the conversation belongs to the current user before deleting
        result = mongo.db.conversations.delete_one({
            "_id": ObjectId(conversation_id),
            "user_id": ObjectId(current_user.id)
        })

        if result.deleted_count == 0:
            return jsonify({'error': 'Conversation not found or access denied'}), 404

        logger.info(f"Deleted conversation: {conversation_id}")
        return jsonify({'success': True, 'id': conversation_id})
    except Exception as e:
        logger.error(f"Error deleting conversation: {str(e)}")
        return jsonify({'error': f'Failed to delete conversation: {str(e)}'}), 500

@app.route('/api/conversation/pin', methods=['PATCH'])
@login_required
def pin_conversation():
    """Pin or unpin a conversation"""
    try:
        data = request.get_json()
        conversation_id = data.get('conversation_id')
        pinned = data.get('pinned', False)
        
        if not conversation_id:
            return jsonify({'error': 'Missing conversation ID'}), 400
            
        # Verify the conversation belongs to the current user and update pin status
        result = mongo.db.conversations.update_one(
            {
                "_id": ObjectId(conversation_id),
                "user_id": ObjectId(current_user.id)
            },
            {"$set": {"pinned": pinned}}
        )
        
        if result.matched_count == 0:
            return jsonify({'error': 'Conversation not found or access denied'}), 404
            
        logger.info(f"{'Pinned' if pinned else 'Unpinned'} conversation: {conversation_id}")
        return jsonify({'success': True, 'pinned': pinned})
        
    except Exception as e:
        logger.error(f"Error pinning conversation: {str(e)}")
        return jsonify({'error': f'Failed to pin conversation: {str(e)}'}), 500

@app.route('/api/user/profile', methods=['GET'])
@login_required
def get_user_profile():
    """Return current user profile information"""
    return jsonify({
        'id': current_user.id,
        'name': current_user.name,
        'email': current_user.email,
        'company': current_user.company,
        'job_title': current_user.job_title,
        'department': current_user.department,
        'role': current_user.role,
        'microsoft_id': current_user.microsoft_id
    })

@app.route('/api/upload', methods=['POST'])
@login_required  
def upload_file():
    """Upload a file for processing"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Add timestamp to prevent filename conflicts
        timestamp = str(int(time.time()))
        filename = f"{timestamp}_{filename}"
        
        upload_dir = os.environ.get('UPLOAD_DIR', 'uploads')
        os.makedirs(upload_dir, exist_ok=True)
        
        file_path = os.path.join(upload_dir, filename)
        file.save(file_path)
        
        return jsonify({
            'message': 'File uploaded successfully',
            'filename': filename,
            'originalName': file.filename
        })
    
    return jsonify({'error': 'File type not allowed'}), 400

@app.route('/api/uploads/<filename>', methods=['GET'])
@login_required
def download_file(filename):
    """
    Serve uploaded files for download
    """
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

def generate_ai_response(user_message, conversation_history):
    """
    Generate an AI response using Azure OpenAI.

    Args:
        user_message (str): The latest message from the user
        conversation_history (list): List of previous messages in the conversation

    Returns:
        str: The AI-generated response
    """
    try:
        # For styling testing purposes, return a simple response if client is not initialized
        if client is None:
            logger.info("Using temporary response for styling testing")
            return f"Hello {current_user.name} from {current_user.company}! This is a temporary response for UI styling testing. The chat functionality will be enabled once Azure OpenAI is properly configured."

        # Format the conversation history for OpenAI
        messages = []

        # Add system message to set up the assistant's behavior
        system_message = f"""You are a helpful Sumersault assistant for {current_user.name}"""
        if current_user.company:
            system_message += f" at {current_user.company}"
        if current_user.job_title:
            system_message += f", who works as {current_user.job_title}"
        if current_user.department:
            system_message += f" in the {current_user.department} department"

        system_message += """. You are branded with green colors and provide accurate, professional, and concise information to help the user. When users upload files, analyze their content and provide relevant insights or assistance."""

        messages.append({
            "role": "system",
            "content": system_message
        })

        # Process conversation history
        for message in conversation_history:
            content = message.get('text', '')

            # If the message has a file attachment
            if message.get('sender') == 'user' and message.get('file'):
                try:
                    file_info = message.get('file')
                    file_path = file_info.get('path', '')
                    file_name = file_info.get('name', 'unnamed-file')
                    file_type = file_info.get('type', '')

                    if os.path.exists(file_path):
                        # For text-based files, include their content in the message
                        if file_type and ('text/' in file_type or file_name.lower().endswith((
                            '.txt', '.md', '.csv', '.json', '.py', '.js', '.html', '.css', '.c', '.cpp', '.h', '.xml'
                        ))):
                            try:
                                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                    file_content = f.read()
                            except Exception as e:
                                logger.error(f"Error reading file {file_name}: {str(e)}")
                                file_content = "Error reading file content"
                        # For binary/non-text files, just mention the file
                        else:
                            file_content = f"\n\nFile attached: {file_name} (binary/non-text file, type: {file_type})"
                    else:
                        file_content = f"\n\nFile attached: {file_name} (file not found on server)"
                except Exception as file_err:
                    logger.error(f"Error processing file content: {str(file_err)}")
                    file_content = f"\n\nFile attached (unable to process content: {str(file_err)})"

            # Add to messages based on sender
            if message.get('sender') == 'user':
                messages.append({"role": "user", "content": content})
            elif message.get('sender') == 'bot':
                messages.append({"role": "assistant", "content": content})

        # Add the latest user message if it's not already in history
        if not conversation_history or conversation_history[-1].get('sender') != 'user' or conversation_history[-1].get('text') != user_message:
            messages.append({"role": "user", "content": user_message})

        # ========== DETAILED LOGGING STARTS HERE ==========

        logger.info("=" * 80)
        logger.info("🚀 AZURE OPENAI API REQUEST")
        logger.info("=" * 80)

        # Log request details
        logger.info(f"📍 Endpoint: {os.getenv('AZURE_OPENAI_ENDPOINT')}")
        logger.info(f"🤖 Model: {os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME')}")
        logger.info(f"👤 User: {current_user.name} ({current_user.email})")
        logger.info(f"💬 Total Messages: {len(messages)}")
        logger.info(f"📝 Latest User Message: {user_message[:100]}...")

        # Log the full payload (be careful with sensitive data)
        logger.info("📦 REQUEST PAYLOAD:")
        request_payload = {
            "model": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            "messages": messages,
            "max_tokens": 1000,
            "temperature": 0.7
        }

        # Log each message in the conversation
        for i, msg in enumerate(messages):
            logger.info(f"  Message {i+1} ({msg['role']}): {msg['content'][:150]}...")

        logger.info(f"⚙️  Parameters: max_tokens=1000, temperature=0.7")

        # Record start time
        import time
        start_time = time.time()

        logger.info("⏳ Sending request to Azure OpenAI...")

        # Call the Azure OpenAI API with streaming enabled
        response = client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            messages=messages,
            stream=True,
            max_tokens=1000,
            temperature=0.7
        )

        # Calculate response time
        response_time = time.time() - start_time

        # ========== DETAILED RESPONSE LOGGING ==========

        logger.info("=" * 80)
        logger.info("📥 AZURE OPENAI API RESPONSE")
        logger.info("=" * 80)

        logger.info(f"⏱️  Response Time: {response_time:.2f} seconds")
        logger.info(f"🆔 Request ID: {getattr(response, 'id', 'N/A')}")
        logger.info(f"🏷️  Model Used: {getattr(response, 'model', 'N/A')}")
        logger.info(f"📊 Usage Stats:")

        # Log token usage if available
        if hasattr(response, 'usage') and response.usage:
            usage = response.usage
            logger.info(f"   📝 Prompt Tokens: {usage.prompt_tokens}")
            logger.info(f"   🔤 Completion Tokens: {usage.completion_tokens}")
            logger.info(f"   🔢 Total Tokens: {usage.total_tokens}")

        # Extract and log the response
        ai_response = response.choices[0].message.content
        finish_reason = response.choices[0].finish_reason

        logger.info(f"🏁 Finish Reason: {finish_reason}")
        logger.info(f"💭 AI Response Length: {len(ai_response)} characters")
        logger.info(f"🤖 AI Response Preview: {ai_response[:200]}...")

        # Log full response (be careful in production)
        logger.info("📄 FULL AI RESPONSE:")
        logger.info(f"{ai_response}")

        logger.info("=" * 80)
        logger.info("✅ AZURE OPENAI REQUEST COMPLETED SUCCESSFULLY")
        logger.info("=" * 80)

        return ai_response

    except Exception as e:
        logger.error("=" * 80)
        logger.error("❌ AZURE OPENAI API ERROR")
        logger.error("=" * 80)
        logger.error(f"🚨 Error Type: {type(e).__name__}")
        logger.error(f"📝 Error Message: {str(e)}")
        logger.error(f"👤 User: {current_user.name} ({current_user.email})")
        logger.error(f"💬 User Message: {user_message}")

        # Log full traceback
        import traceback
        logger.error(f"🔍 Full Traceback:")
        logger.error(traceback.format_exc())
        logger.error("=" * 80)

        return f"I apologize, but I encountered an error while processing your request. Please try again later. Error: {str(e)}"
        
# Admin routes for user management (protected by role check)
@app.route('/admin/users', methods=['GET'])
@login_required
def admin_users():
    # Check if the current user has admin role
    if current_user.role != 'admin':
        return jsonify({"error": "Access denied"}), 403

    # List all users
    users = mongo.db.users.find({})
    user_list = []

    for user in users:
        user_data = {
            'id': str(user['_id']),
            'email': user['email'],
            'name': user.get('name', ''),
            'company': user.get('company', ''),
            'job_title': user.get('job_title', ''),
            'department': user.get('department', ''),
            'role': user.get('role', 'user'),
            'last_login': user.get('last_login', ''),
            'created_at': user.get('created_at', '')
        }
        user_list.append(user_data)

    return jsonify(user_list)

@app.route('/admin/user/<user_id>/role', methods=['PUT'])
@login_required
def admin_update_role(user_id):
    # Check if the current user has admin role
    if current_user.role != 'admin':
        return jsonify({"error": "Access denied"}), 403

    try:
        data = request.json
        role = data.get('role')

        if role not in ['user', 'admin']:
            return jsonify({"error": "Invalid role"}), 400

        # Update the user role
        result = mongo.db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"role": role}}
        )

        if result.matched_count == 0:
            return jsonify({"error": "User not found"}), 404

        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error updating user role: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Create first admin user on startup if none exists
def ensure_admin_exists():
    admin_email = os.environ.get("ADMIN_EMAIL")
    if not admin_email:
        logger.warning("No ADMIN_EMAIL set in environment variables")
        return

    existing_admin = mongo.db.users.find_one({"role": "admin"})
    if not existing_admin:
        # Check if the admin email user exists and promote them
        admin_user = mongo.db.users.find_one({"email": admin_email})
        if admin_user:
            mongo.db.users.update_one(
                {"_id": admin_user['_id']},
                {"$set": {"role": "admin"}}
            )
            logger.info(f"Promoted existing user to admin: {admin_email}")
        else:
            logger.info(f"Admin user {admin_email} not found. They will be created as admin when they first log in.")

@app.route('/api/chat/stream', methods=['POST'])
@login_required
def chat_stream():
    """Streaming chat endpoint for thinking aloud feature"""
    try:
        data = request.get_json()
        user_message = data.get('message', '')
        conversation_id = data.get('conversation_id', '')
        
        # Debug logging to see what data we're receiving
        logger.info(f"Streaming request data: {data}")
        
        if not user_message:
            return jsonify({'error': 'No message provided'}), 400
            
        if not conversation_id:
            return jsonify({'error': 'No conversation ID provided'}), 400
        
        # Verify the conversation belongs to the current user
        conversation = mongo.db.conversations.find_one({
            "_id": ObjectId(conversation_id),
            "user_id": ObjectId(current_user.id)
        })
        
        if not conversation:
            return jsonify({'error': 'Conversation not found or access denied'}), 404
        
        def generate_stream():
            try:
                # Save the user message first
                user_msg = {
                    "id": str(ObjectId()),
                    "text": user_message,
                    "sender": "user",
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                # Add file info if present
                if 'file' in data and data['file']:
                    user_msg["file"] = data['file']
                
                # Prepare messages for the AI
                if current_user and hasattr(current_user, 'username') and hasattr(current_user, 'company'):
                    system_message = f"You are a helpful Sumersault assistant for {current_user.username} at {current_user.company}. You are branded with green colors and provide accurate, professional, and helpful assistance."
                else:
                    system_message = "You are a helpful Sumersault assistant. You are branded with green colors and provide accurate, professional, and helpful assistance."
                
                messages = [{"role": "system", "content": system_message}]
                
                # Add conversation history
                for msg in conversation.get('messages', []):
                    if msg.get('sender') == 'user':
                        messages.append({"role": "user", "content": msg.get('text', '')})
                    elif msg.get('sender') == 'bot':
                        messages.append({"role": "assistant", "content": msg.get('text', '')})
                
                # Add the current user message with file content if present
                message_content = user_message
                if 'file' in data and data['file'] and 'uploadedPath' in data['file']:
                    # Read file content if it's a text file
                    file_path = os.path.join(os.environ.get('UPLOAD_DIR', 'uploads'), data['file']['uploadedPath'])
                    if os.path.exists(file_path):
                        try:
                            # Try to read as text file
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                file_content = f.read()
                            message_content = f"{user_message}\n\nHere is the content of the attached file '{data['file']['name']}':\n\n```\n{file_content}\n```"
                        except UnicodeDecodeError:
                            # If not a text file, just mention the file
                            message_content = f"{user_message}\n\nFile attached: {data['file']['name']} (binary file, cannot display content)"
                        except Exception as e:
                            logger.error(f"Error reading file: {e}")
                            message_content = f"{user_message}\n\nFile attached: {data['file']['name']} (error reading file: {str(e)})"
                    else:
                        message_content = f"{user_message}\n\nFile '{data['file']['name']}' was attached but file not found on server"
                        
                logger.info(f"Final message content being sent to AI: {message_content[:200]}...")
                
                messages.append({"role": "user", "content": message_content})
                
                # Call Azure OpenAI with streaming
                response = client.chat.completions.create(
                    model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
                    messages=messages,
                    stream=True,
                    max_tokens=1000,
                    temperature=0.7
                )
                
                # Collect the streamed response
                ai_response_text = ""
                
                # Stream the response
                for chunk in response:
                    if hasattr(chunk, 'choices') and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        if hasattr(delta, 'content') and delta.content is not None:
                            content = delta.content
                            ai_response_text += content
                            yield f"data: {json.dumps({'content': content})}\n\n"
                
                # Save both messages to the database
                ai_msg = {
                    "id": str(ObjectId()),
                    "text": ai_response_text,
                    "sender": "bot",
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                # Update the conversation with both messages
                mongo.db.conversations.update_one(
                    {"_id": ObjectId(conversation_id)},
                    {"$push": {"messages": {"$each": [user_msg, ai_msg]}}}
                )
                
                # Send completion signal
                yield f"data: {json.dumps({'done': True})}\n\n"
                
            except Exception as e:
                logger.error(f"Error in streaming: {str(e)}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        
        return Response(
            generate_stream(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Access-Control-Allow-Origin': '*'
            }
        )
        
    except Exception as e:
        logger.error(f"Error in streaming chat endpoint: {str(e)}")
        return jsonify({'error': 'Failed to process streaming chat request'}), 500

# Add the AuthorizedUser class and routes in the correct location
class AuthorizedUser:
    def __init__(self, email):
        self.email = email
        self.added_date = datetime.utcnow()

@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    return render_template('admin.html')

@app.route('/api/admin/authorized-users', methods=['GET'])
@login_required
def get_authorized_users():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    users = list(mongo.db.authorized_users.find({}, {'_id': 1, 'email': 1, 'added_date': 1}))
    for user in users:
        user['_id'] = str(user['_id'])
    return jsonify(users)

@app.route('/api/admin/authorized-users', methods=['POST'])
@login_required
def add_authorized_user():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    email = data.get('email')
    
    if not email:
        return jsonify({'success': False, 'message': 'Email is required'}), 400
    
    # Check if user already exists
    existing_user = mongo.db.authorized_users.find_one({'email': email})
    if existing_user:
        return jsonify({'success': False, 'message': 'User already exists'}), 400
    
    # Add new authorized user
    new_user = AuthorizedUser(email)
    mongo.db.authorized_users.insert_one(new_user.__dict__)
    
    return jsonify({'success': True, 'message': 'User added successfully'})

@app.route('/api/admin/authorized-users/<user_id>', methods=['DELETE'])
@login_required
def remove_authorized_user(user_id):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        result = mongo.db.authorized_users.delete_one({'_id': ObjectId(user_id)})
        if result.deleted_count:
            return jsonify({'success': True, 'message': 'User removed successfully'})
        return jsonify({'success': False, 'message': 'User not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400

if __name__ == "__main__":
    # Ensure admin user exists on startup
    ensure_admin_exists()
    app.run(host="0.0.0.0", port=5001, debug=True)