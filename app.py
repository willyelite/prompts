import os
import json
import re # Importa a biblioteca de expressões regulares para a busca no texto
import requests
from flask import Flask, render_template, request, url_for, flash, redirect, session, jsonify, make_response
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, current_user, logout_user, login_required
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError
from flask_session import Session

# --- CONFIGURAÇÃO ---
load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'd9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4')

api_key = os.getenv("NVIDIA_API_KEY")

db_url = os.getenv('DATABASE_URL')
if not db_url: raise ValueError("DATABASE_URL not set")
if db_url.startswith("postgres://"): db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- CONFIGURAÇÃO DO FLASK-SESSION ---
app.config["SESSION_TYPE"] = "sqlalchemy"
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_USE_SIGNER"] = True
db = SQLAlchemy(app)
app.config["SESSION_SQLALCHEMY"] = db
sess = Session(app)

bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = "Por favor, faça login para acessar esta página."
login_manager.login_message_category = "info"


# --- MODELOS E FORMULÁRIOS ---
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(60), nullable=False)

class SavedCharacter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    concept = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('saved_characters', lazy=True))

class SavedScenario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    concept = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('saved_scenarios', lazy=True))

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
            redirect_target = request.form.get('redirect_choice')
            if redirect_target == 'biblioteca':
                return redirect(url_for('biblioteca'))
            else:
                return redirect(url_for('oficina'))
        else:
            flash('Login falhou. Verifique o email e a senha.', 'danger')
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
        flash('Sua conta foi criada! Agora você pode fazer login.', 'success')
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
            flash('Adicione pelo menos um personagem para continuar.', 'danger')
            return redirect(url_for('oficina'))
        return redirect(url_for('detalhes'))
    return render_template('oficina.html', 
                           saved_characters=session.get('characters', []), 
                           saved_scenario=session.get('scenario', {}))

@app.route('/detalhes', methods=['GET', 'POST'])
@login_required
def detalhes():
    if 'characters' not in session or not session.get('characters'):
        flash('Você precisa definir personagens antes de continuar. Comece pela oficina.', 'info')
        return redirect(url_for('oficina'))
    if request.method == 'POST':
        session['details'] = {key: request.form.get(key) for key in request.form}
        session['details']['dialogues'] = json.loads(request.form.get('dialogue_data', '[]'))
        return redirect(url_for('resumo'))
    return render_template('detalhes.html')

@app.route('/resumo')
@login_required
def resumo():
    if 'details' not in session:
        flash('Você precisa passar pelos detalhes antes de ver o resumo.', 'info')
        return redirect(url_for('detalhes'))
    server_data = {
        "characters": session.get('characters', []),
        "details": session.get('details', {}),
        "scenario": session.get('scenario', {})
    }
    return render_template('resumo.html', server_data=server_data)


# --- ROTAS DA BIBLIOTECA ---
@app.route('/biblioteca')
@login_required
def biblioteca():
    session.clear()
    user_characters = SavedCharacter.query.filter_by(user_id=current_user.id).order_by(SavedCharacter.name).all()
    user_scenarios = SavedScenario.query.filter_by(user_id=current_user.id).order_by(SavedScenario.name).all()
    return render_template('biblioteca.html', 
                           characters=user_characters, 
                           scenarios=user_scenarios)

@app.route('/biblioteca/carregar', methods=['POST'])
@login_required
def carregar_da_biblioteca():
    session.clear()
    char_ids = request.form.getlist('character_ids')
    scen_id = request.form.get('scenario_id')
    loaded_characters = []
    if char_ids:
        characters_from_db = db.session.query(SavedCharacter).filter(SavedCharacter.id.in_(char_ids)).all()
        for i, char_db in enumerate(characters_from_db):
            if char_db.user_id == current_user.id:
                loaded_characters.append({
                    'id': i + 1, 'name': char_db.name,
                    'concept': char_db.concept, 'description': char_db.description
                })
    loaded_scenario = {}
    if scen_id:
        scenario_from_db = db.session.get(SavedScenario, int(scen_id))
        if scenario_from_db and scenario_from_db.user_id == current_user.id:
            loaded_scenario = {
                'name': scenario_from_db.name,
                'description': scenario_from_db.description
            }
    if not loaded_characters:
        flash('Selecione pelo menos um personagem para carregar.', 'danger')
        return redirect(url_for('biblioteca'))
    session['characters'] = loaded_characters
    session['scenario'] = loaded_scenario
    return redirect(url_for('detalhes'))


@app.route('/delete_asset/<string:asset_type>/<int:asset_id>', methods=['POST'])
@login_required
def delete_asset(asset_type, asset_id):
    try:
        if asset_type == 'character': asset = db.session.get(SavedCharacter, asset_id)
        elif asset_type == 'scenario': asset = db.session.get(SavedScenario, asset_id)
        else: return jsonify({'success': False, 'message': 'Tipo de ativo inválido.'}), 400
        if not asset: return jsonify({'success': False, 'message': 'Ativo não encontrado.'}), 404
        if asset.user_id != current_user.id: return jsonify({'success': False, 'message': 'Não autorizado.'}), 403
        db.session.delete(asset)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Ativo apagado com sucesso.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erro no servidor: {e}'}), 500


# --- FUNÇÕES E ROTA DE IA ---

def generate_ia_content(instruction):
    if not api_key:
        return "Erro: A chave da API da NVIDIA não foi configurada no servidor."

    invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }

    payload = {
        "model": "meta/llama3-8b-instruct",
        "messages": [
            {
                "content": instruction,
                "role": "user"
            }
        ],
        "temperature": 0.7,
        "top_p": 1.0,
        "max_tokens": 2048,
        "stream": False
    }

    try:
        response = requests.post(invoke_url, headers=headers, json=payload)
        response.raise_for_status()
        
        response_body = response.json()
        ai_content = response_body['choices'][0]['message']['content']
        return ai_content.strip()

    except requests.exceptions.RequestException as e:
        error_details = f"Erro de conexão com a API da NVIDIA: {e}"
        if e.response is not None:
            error_details += f" | Status: {e.response.status_code} | Resposta: {e.response.text}"
        return error_details
    except (KeyError, IndexError) as e:
        return f"Erro ao processar a resposta da API da NVIDIA: formato inesperado. {e}"
    except Exception as e:
        return f"Erro na IA: {e}"


@app.route('/montar-prompt', methods=['POST'])
@login_required
def montar_prompt():
    data = request.json
    characters = data.get('characters', [])
    scenario = data.get('scenario', {})
    details = data.get('details', {})
    language = details.get('language', 'English') 
    
    character_concepts = "\n".join([f"- Character Concept for '{c.get('name')}': {c.get('description')}" for c in characters])
    scenario_concept = f"- Scenario Concept for '{scenario.get('name')}': {scenario.get('description')}"
    
    dialogue_lines_pt_br = []
    if details.get('dialogues'):
      for d in details.get('dialogues', []):
          char_name = next((c['name'] for c in characters if str(c['id']) == str(d.get('charId'))), "Character")
          dialogue_lines_pt_br.append(f"- {char_name}: \"{d.get('text')}\"")

    # MUDANÇA: Instrução final completamente refeita para ser mais direta, procedural e rigorosa.
    final_assembly_instruction = f"""
    You are a professional prompt engineer. Your only task is to generate a complete video prompt by precisely following the structure and rules below.

    **USER'S RAW DATA:**
    Action Context: "{details.get('action_context')}"
    Visual Style: "{details.get('visual_style')}"
    Character Concepts:
      {character_concepts}
    Scenario Concept:
      {scenario_concept}
    Dialogue Sequence (to be translated to {language}):
      {"\n".join(dialogue_lines_pt_br) if dialogue_lines_pt_br else "No dialogue provided."}

    **GENERATION TASK - Follow this structure EXACTLY:**

    🎬 Prompt Title:
    [Generate a 1-3 word title in ENGLISH based on the Action Context]

    🌍 Scene Setup:
    <scen_{scenario.get('name', 'default').replace(' ', '_')}_start>
    Location: [Expand the Scenario Concept into a detailed description of the location.] Lighting: [Describe the lighting of the scene.] Atmosphere: [Describe the atmosphere, sounds, and smells.]
    </scen_{scenario.get('name', 'default').replace(' ', '_')}_end>

    {"\n---\n\n".join([f"""👤 Character Profile: {c.get('name')}
    <char_{c.get('name').replace(' ', '_')}_start>
    Age: [Expand the Character Concept for '{c.get('name')}' into their age.] Ethnicity: [Describe their ethnicity.] Height: [Describe their height and build.] Face: [Describe their facial features.] Eyes: [Describe their eyes.]Hair: [Describe their hair.]
    </char_{c.get('name').replace(' ', '_')}_end>
    Attire: [Describe what this character is wearing in this specific scene.] Posture: [Describe their posture.] Facial Expression: [Describe their facial expression.]
""" for c in characters])}

    🎞️ Scene Breakdown
    Scene 01 (0.0s – 4.5s):
    Action: [Describe what the characters are doing, ensuring the action is directly inspired by the "Action Context".]
    Dialogue ({language}): [Translate the first dialogue line and attribute it in the format: Character Name says, "Translated text.".]
    Camera: [Describe a camera movement and framing for this scene.]
    Cinematography: [Describe a technical detail for this scene.]

    Scene 02 (4.5s – 8.0s):
    Action: [Describe the continuing action for this scene.]
    Dialogue ({language}): [Translate the second dialogue line and attribute it.]
    Camera: [Describe a different camera movement and framing.]
    Cinematography: [Describe another technical detail.]

    ⚙️ Final Instructions for IA:
    Visual Style: {details.get('visual_style')} shot on an ARRI Alexa camera. Color Grading: [Describe a color grading style.] Duration: 8 seconds. Language: {language} with perfect lip-sync. Audio: [Describe the audio mix.] Output: No watermarks, no subtitles.
    """
    final_prompt = generate_ia_content(final_assembly_instruction)
    return jsonify({'prompt': final_prompt})


@app.route('/save_from_prompt', methods=['POST'])
@login_required
def save_from_prompt():
    data = request.json
    component_type = data.get('component_type')
    component_name = data.get('component_name')
    full_prompt_text = data.get('full_prompt_text')

    if not all([component_type, component_name, full_prompt_text]):
        return jsonify({'success': False, 'message': 'Dados incompletos.'}), 400

    sanitized_name = component_name.replace(' ', '_')
    
    if component_type == 'character':
        start_tag = f"<char_{sanitized_name}_start>"
        end_tag = f"</char_{sanitized_name}_end>"
    elif component_type == 'scenario':
        start_tag = f"<scen_{sanitized_name}_start>"
        end_tag = f"</scen_{sanitized_name}_end>"
    else:
        return jsonify({'success': False, 'message': 'Tipo de componente inválido.'}), 400

    try:
        pattern = re.compile(f"{re.escape(start_tag)}(.*?){re.escape(end_tag)}", re.DOTALL)
        match = pattern.search(full_prompt_text)
        
        if not match:
            return jsonify({'success': False, 'message': f'Não foi possível encontrar a descrição para "{component_name}" no prompt.'}), 404

        description = match.group(1).strip()

        if component_type == 'character':
            exists = SavedCharacter.query.filter_by(user_id=current_user.id, name=component_name).first()
            if exists:
                return jsonify({'success': True, 'message': f'"{component_name}" já estava salvo.'})
            
            new_char = SavedCharacter(
                name=component_name,
                concept=description,
                description=description,
                user_id=current_user.id
            )
            db.session.add(new_char)

        elif component_type == 'scenario':
            exists = SavedScenario.query.filter_by(user_id=current_user.id, name=component_name).first()
            if exists:
                return jsonify({'success': True, 'message': f'"{component_name}" já estava salvo.'})

            new_scen = SavedScenario(
                name=component_name,
                concept=description,
                description=description,
                user_id=current_user.id
            )
            db.session.add(new_scen)
        
        db.session.commit()
        return jsonify({'success': True, 'message': f'"{component_name}" salvo com sucesso na biblioteca!'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erro no servidor ao salvar: {e}'}), 500


# --- COMANDOS DE ADMINISTRAÇÃO VIA TERMINAL ---
@app.cli.command("init-db")
def init_db_command():
    """Apaga todas as tabelas e as recria do zero. Perde todos os dados."""
    try:
        print("Iniciando o reset do banco de dados...")
        db.drop_all()
        db.create_all()
        print("Banco de dados zerado e recriado com sucesso.")
        print("Lembre-se de criar uma nova conta de usuário.")
    except Exception as e:
        print(f"Ocorreu um erro durante o reset: {e}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)