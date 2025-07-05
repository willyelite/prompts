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
    return render_template('resumo.html')

# --- ROTAS DA BIBLIOTECA ---

@app.route('/biblioteca')
@login_required
def biblioteca():
    session.clear()
    user_characters = SavedCharacter.query.filter_by(user_id=current_user.id).order_by(SavedCharacter.name).all()
    user_scenarios = SavedScenario.query.filter_by(user_id=current_user.id).order_by(SavedScenario.concept).all()
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
                    'id': i + 1,
                    'name': char_db.name,
                    'concept': char_db.concept,
                    'description': char_db.description
                })
    
    loaded_scenario = {}
    if scen_id:
        scenario_from_db = db.session.get(SavedScenario, int(scen_id))
        if scenario_from_db and scenario_from_db.user_id == current_user.id:
            loaded_scenario = {
                'concept': scenario_from_db.concept,
                'description': scenario_from_db.description
            }

    if not loaded_characters:
        flash('Selecione pelo menos um personagem para carregar.', 'danger')
        return redirect(url_for('biblioteca'))

    session['characters'] = loaded_characters
    session['scenario'] = loaded_scenario
    
    return redirect(url_for('detalhes'))


@app.route('/save_components', methods=['POST'])
@login_required
def save_components():
    characters = session.get('characters', [])
    scenario = session.get('scenario', {})

    if not characters and not scenario.get('concept'):
        return jsonify({'success': False, 'message': 'Não há nada na sessão atual para salvar.'}), 400

    try:
        saved_count = 0
        for char_data in characters:
            exists = SavedCharacter.query.filter_by(user_id=current_user.id, name=char_data['name']).first()
            if not exists:
                new_char = SavedCharacter(
                    name=char_data['name'],
                    concept=char_data['concept'],
                    description=char_data['description'],
                    user_id=current_user.id
                )
                db.session.add(new_char)
                saved_count += 1

        if scenario.get('concept'):
            exists = SavedScenario.query.filter_by(user_id=current_user.id, concept=scenario['concept']).first()
            if not exists:
                new_scen = SavedScenario(
                    concept=scenario['concept'],
                    description=scenario['description'],
                    user_id=current_user.id
                )
                db.session.add(new_scen)
                saved_count += 1
        
        if saved_count > 0:
            db.session.commit()
            return jsonify({'success': True, 'message': f'{saved_count} novo(s) componente(s) salvo(s) na sua biblioteca!'})
        else:
            return jsonify({'success': True, 'message': 'Todos os componentes desta sessão já estavam salvos.'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erro no servidor: {e}'}), 500

@app.route('/delete_asset/<string:asset_type>/<int:asset_id>', methods=['POST'])
@login_required
def delete_asset(asset_type, asset_id):
    try:
        if asset_type == 'character':
            asset = db.session.get(SavedCharacter, asset_id)
        elif asset_type == 'scenario':
            asset = db.session.get(SavedScenario, asset_id)
        else:
            return jsonify({'success': False, 'message': 'Tipo de ativo inválido.'}), 400

        if not asset:
            return jsonify({'success': False, 'message': 'Ativo não encontrado.'}), 404
        
        if asset.user_id != current_user.id:
            return jsonify({'success': False, 'message': 'Não autorizado.'}), 403

        db.session.delete(asset)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Ativo apagado com sucesso.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erro no servidor: {e}'}), 500


# --- MICRO-ROTAS E FUNÇÕES FINAIS (IA) ---
def generate_ia_content(instruction):
    if not api_key:
        return "Erro: A chave da API do Gemini não foi configurada no servidor."
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
    
    character_prompts = [f"- Technical Sheet for '{c.get('name')}': {c.get('description')}" for c in characters]
    
    dialogue_prompts = []
    for d in details.get('dialogues', []):
        char_name = next((c['name'] for c in characters if c['id'] == d.get('charId')), "Character")
        dialogue_prompts.append(f"- {char_name}: \"{d.get('text')}\"")

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

# --- ROTA DE ADMINISTRAÇÃO PARA RESETAR O BANCO DE DADOS ---
@app.route('/reset-database')
def reset_database():
    # ATENÇÃO: Esta rota apaga TODOS os dados. Use com cuidado.
    # A "senha" na URL é uma medida de segurança mínima.
    secret_key = request.args.get('secret')
    if secret_key != 'startfresh': # Você pode mudar 'startfresh' para qualquer senha que quiser
        return "Acesso não autorizado.", 403

    try:
        flash('Iniciando reset do banco de dados...', 'info')
        # Apaga todas as tabelas
        db.drop_all()
        # Cria todas as tabelas novamente com base nos modelos
        db.create_all()
        flash('Banco de dados zerado e recriado com sucesso! Por favor, crie uma nova conta.', 'success')
        return redirect(url_for('register'))
    except Exception as e:
        return f"Ocorreu um erro durante o reset: {e}", 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)