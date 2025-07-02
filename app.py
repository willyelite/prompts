import os
import json
import google.generativeai as genai
from flask import Flask, render_template, request, url_for, flash, redirect, session, jsonify, make_response
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, current_user, logout_user, login_required
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError

# --- CONFIGURAÇÃO ---
load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'd9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4')
api_key = os.getenv("GEMINI_API_KEY")
if api_key: genai.configure(api_key=api_key)

db_url = os.getenv('DATABASE_URL')
if not db_url: raise ValueError("DATABASE_URL not set")
if db_url.startswith("postgres://"): db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- MODELOS E FORMULÁRIOS ---
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(60), nullable=False)

class RegistrationForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Senha', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirmar Senha', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Cadastrar')
    def validate_email(self, email):
        if User.query.filter_by(email=email.data).first():
            raise ValidationError('Este email já está em uso.')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Senha', validators=[DataRequired()])
    submit = SubmitField('Entrar')

with app.app_context():
    db.create_all()
    
# --- ROTAS DE AUTENTICAÇÃO ---
@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('oficina'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password_hash, form.password.data):
            login_user(user, remember=True)
            return redirect(url_for('oficina'))
    return render_template('login.html', form=form)

@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('oficina'))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(email=form.email.data, password_hash=hashed_password)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route("/logout")
def logout():
    logout_user()
    session.clear()
    response = make_response(redirect(url_for('goodbye')))
    response.set_cookie('remember_token', '', expires=0, path='/')
    return response

@app.route("/goodbye")
def goodbye():
    return render_template('goodbye.html')

# --- ROTAS DO FLUXO "WIZARD" ---
@app.route('/')
@login_required
def home():
    session.clear()
    return redirect(url_for('oficina'))

@app.route('/oficina', methods=['GET', 'POST'])
@login_required
def oficina():
    if request.method == 'POST':
        session['characters'] = json.loads(request.form.get('scene_characters_data', '[]'))
        session['scenario'] = json.loads(request.form.get('scene_scenario_data', '{}'))
        if not session.get('characters'):
            return redirect(url_for('oficina'))
        return redirect(url_for('detalhes'))
    return render_template('oficina.html', 
                           saved_characters=session.get('characters', []), 
                           saved_scenario=session.get('scenario', {}))

# <<< ROTA CORRIGIDA PARA RENDERIZAR O TEMPLATE >>>
@app.route('/detalhes', methods=['GET', 'POST'])
@login_required
def detalhes():
    if 'characters' not in session or not session.get('characters'):
        return redirect(url_for('oficina'))
    if request.method == 'POST':
        session['details'] = {key: request.form.get(key) for key in request.form}
        session['details']['dialogues'] = json.loads(request.form.get('dialogue_data', '[]'))
        return redirect(url_for('resumo'))
    return render_template('detalhes.html')

# <<< ROTA CORRIGIDA PARA RENDERIZAR O TEMPLATE >>>
@app.route('/resumo')
@login_required
def resumo():
    if 'details' not in session:
        return redirect(url_for('detalhes'))
    return render_template('resumo.html')

# --- MICRO-ROTAS E FUNÇÕES FINAIS ---
def generate_ia_content(instruction):
    model = genai.GenerativeModel('gemini-1.5-flash')
    try:
        response = model.generate_content(instruction)
        return response.text.strip()
    except Exception as e: return f"Erro na IA: {e}"

@app.route('/generate/character_description', methods=['POST'])
@login_required
def generate_character_description():
    concept = request.json.get('concept')
    instruction = f"Gere uma ficha técnica de personagem EM PORTUGUÊS com base neste conceito: '{concept}'. Use o seguinte formato de lista: \n- Idade: \n- Etnia: \n- Rosto: \n- Olhos: \n- Cabelo: \n- Físico: \n- Vestimenta: "
    description = generate_ia_content(instruction)
    return jsonify({'description': description})

@app.route('/generate/scene_description', methods=['POST'])
@login_required
def generate_scene_description():
    concept = request.json.get('concept')
    instruction = f"Gere uma ficha técnica de cenário EM PORTUGUÊS com base neste conceito: '{concept}'. Use o seguinte formato de lista: \n- Localização: \n- Elementos Chave: \n- Iluminação: \n- Atmosfera:"
    description = generate_ia_content(instruction)
    return jsonify({'description': description})

@app.route('/generate/summary', methods=['POST'])
@login_required
def generate_summary():
    concept = request.json.get('concept')
    instruction = f"Resuma o seguinte conceito de personagem em um nome curto e impactante de 1 a 2 palavras em português. Conceito: '{concept}'"
    summary = generate_ia_content(instruction)
    return jsonify({'summary': summary})

@app.route('/montar-prompt', methods=['POST'])
@login_required
def montar_prompt():
    data = request.json
    characters = data.get('characters', [])
    scenario = data.get('scenario', {})
    details = data.get('details', {})
    
    # Coleta de dados (sem alterações aqui)
    character_prompts = [f"- Technical Sheet for '{c.get('name')}': {c.get('description')}" for c in characters]
    
    dialogue_prompts = []
    for d in details.get('dialogues', []):
        char_name = next((c['name'] for c in characters if c['id'] == d['charId']), "Character")
        dialogue_prompts.append(f"- {char_name}: \"{d.get('text')}\"")

    # <<< NOVA INSTRUÇÃO TOTALMENTE EM INGLÊS E COM AS NOVAS REGRAS >>>
    final_assembly_instruction = f"""
    You are an expert screenwriter and art director for generative AI. Your task is to transform the raw data below into a final, highly structured, and detailed video prompt. Follow the model and rules strictly.

    **RULES:**
    1.  **Output Language:** All structural text (headers, technical descriptions, camera directions) MUST be in ENGLISH.
    2.  **Dialogue Language:** The character dialogues provided in the 'Dialogue Sequence' MUST remain in BRAZILIAN PORTUGUESE (PT-BR) exactly as given. Do not translate them.
    3.  **Prompt Title:** Create a short, impactful title of 1 to 3 words summarizing the main character and the scene. (e.g., "Pirate on a Ship", "Detective in Rain").
    4.  **Creative Expansion:** Take the Portuguese technical sheets for the scene and characters and expand them into rich, evocative ENGLISH descriptions under the 'Scene Setup' and 'Character' sections.
    5.  **Scene Creation:** Based on the 'Action Context' and the 'Dialogue Sequence', create "Scene" sections (Scene 01, Scene 02, etc.). Each scene must have an estimated duration, a description of the action, the corresponding dialogue, and technical details for Camera, Light, and Audio.

    **RAW DATA TO TRANSFORM (Source data is in Portuguese):**
    - **Action Context (Use for the story):** "{details.get('action_context')}"
    - **Scene Technical Sheet:** "{scenario.get('description')}"
    - **Character Technical Sheets:**
      {", ".join(character_prompts)}
    - **Dialogue Sequence (KEEP IN PORTUGUESE):**
      {", ".join(dialogue_prompts)}
    - **General Technical Details:**
      - Visual Style: "{details.get('visual_style')}"
      - Camera Style: "{details.get('camera_style')}"
      - Estimated Total Duration: 8 seconds (to be divided among scenes)
      - Aspect Ratio: 16:9

    **REQUIRED OUTPUT MODEL (Fill this template with the transformed data):**

    **Prompt Title:**
    [Generate the 1-3 word title here]

    **Scene Setup:**
    [Detailed and expanded description of the environment, combining the Scene Technical Sheet with the context, weather, atmosphere, and lighting. IN ENGLISH.]

    **Character – [Character Name]:**
    [Detailed and expanded description of the character, using their Technical Sheet. IN ENGLISH.]

    **🎞️ Scene 01 (0.0s – 4.0s):**
    [Description of the action for the first scene, incorporating the first dialogue. IN ENGLISH.]
    **🗣️ Dialogue (PT-BR):**
    "[First dialogue from the sequence. IN PORTUGUESE.]"
    **Camera:** [Describe camera movement and shot type. IN ENGLISH.]
    **Light:** [Describe the scene's lighting. IN ENGLISH.]
    **Audio:** [Describe the background audio. IN ENGLISH.]
    **Focus:** [Describe the camera's focus. IN ENGLISH.]
    **Mood:** [Describe the mood of the scene. IN ENGLISH.]

    **🎞️ Scene 02 (4.0s – 8.0s):**
    [Description of the action for the second scene, incorporating the second dialogue. IN ENGLISH.]
    **🗣️ Dialogue (PT-BR):**
    "[Second dialogue from the sequence. IN PORTUGUESE.]"
    **Camera:** [Describe camera movement and shot type. IN ENGLISH.]
    **Light:** [Describe the scene's lighting. IN ENGLISH.]
    **Audio:** [Describe the background audio. IN ENGLISH.]
    **Focus:** [Describe the camera's focus. IN ENGLISH.]
    **Atmosphere:** [Describe the atmosphere of the scene. IN ENGLISH.]

    **(Continue with more scenes if there are more dialogues)**

    **⚙️ Final AI Instructions:**
    **Duration:** 8 seconds
    **Aspect Ratio:** 16:9
    **Dialogue:** Brazilian Portuguese (PT-BR), lip sync enabled
    **Focus:** Always on the character
    **Visual Style:** [Use the Visual Style from the Technical Details. IN ENGLISH.]
    **No subtitles, no watermarks**
    **Audio:** Clean, continuous beat, no additional voiceover
    """
    
    final_prompt = generate_ia_content(final_assembly_instruction)
    return jsonify({'prompt': final_prompt})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)