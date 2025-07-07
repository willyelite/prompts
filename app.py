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
from flask_migrate import Migrate

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
migrate = Migrate(app, db)
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

# ALTERADO: User agora tem um relacionamento com Project
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(60), nullable=False)
    projects = db.relationship('Project', backref='user', lazy=True, cascade="all, delete-orphan")

# NOVO: A classe Project que armazena os componentes
class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    characters = db.relationship('SavedCharacter', backref='project', lazy='dynamic', cascade="all, delete-orphan")
    scenarios = db.relationship('SavedScenario', backref='project', lazy='dynamic', cascade="all, delete-orphan")

# ALTERADO: SavedCharacter agora pertence a um Project
class SavedCharacter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    concept = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)

# ALTERADO: SavedScenario agora pertence a um Project
class SavedScenario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    concept = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)

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


# --- ROTAS DA BIBLIOTECA E PROJETOS (Grandes Mudanças) ---

@app.route('/biblioteca')
@login_required
def biblioteca():
    session.clear()
    projects = Project.query.filter_by(user_id=current_user.id).order_by(Project.name).all()
    
    # Prepara as listas para o HTML
    for project in projects:
        project.characters_list = project.characters.order_by(SavedCharacter.name).all()
        project.scenarios_list = project.scenarios.order_by(SavedScenario.name).all()

    # NOVO: Cria uma lista de dicionários simples para o JavaScript
    projects_for_js = []
    for p in projects:
        projects_for_js.append({
            'id': p.id,
            'name': p.name
        })

    # Passa AMBAS as versões para o template
    return render_template(
        'biblioteca.html', 
        projects=projects, 
        projects_for_js=projects_for_js
    )
    
@app.route('/project/create', methods=['POST'])
@login_required
def create_project():
    project_name = request.form.get('project_name')
    if project_name:
        new_project = Project(name=project_name, user_id=current_user.id)
        db.session.add(new_project)
        db.session.commit()
        flash(f'Projeto "{project_name}" criado com sucesso!', 'success')
    else:
        flash('O nome do projeto não pode ser vazio.', 'danger')
    return redirect(url_for('biblioteca'))

# Em app.py, adicione esta rota no lugar da start_from_project

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
            # Validação de segurança: o usuário é dono do projeto deste personagem?
            if char_db.project.user_id == current_user.id:
                loaded_characters.append({
                    'id': i + 1, 'name': char_db.name,
                    'concept': char_db.concept, 'description': char_db.description
                })
    
    loaded_scenario = {}
    if scen_id:
        scenario_from_db = db.session.get(SavedScenario, int(scen_id))
        # Validação de segurança: o usuário é dono do projeto deste cenário?
        if scenario_from_db and scenario_from_db.project.user_id == current_user.id:
            loaded_scenario = {
                'name': scenario_from_db.name,
                'description': scenario_from_db.description
            }
            
    if not loaded_characters and not loaded_scenario:
        flash('Selecione pelo menos um componente para carregar.', 'danger')
        return redirect(url_for('biblioteca'))

    session['characters'] = loaded_characters
    session['scenario'] = loaded_scenario
    # Guarda o projeto de onde os itens vieram, para saber onde salvar depois
    if loaded_characters:
         session['current_project_id'] = loaded_characters[0]['project_id'] = characters_from_db[0].project_id
    elif loaded_scenario:
         session['current_project_id'] = loaded_scenario['project_id'] = scenario_from_db.project_id

    return redirect(url_for('oficina'))


@app.route('/delete_asset/<string:asset_type>/<int:asset_id>', methods=['POST'])
@login_required
def delete_asset(asset_type, asset_id):
    try:
        if asset_type == 'character': asset = db.session.get(SavedCharacter, asset_id)
        elif asset_type == 'scenario': asset = db.session.get(SavedScenario, asset_id)
        else: return jsonify({'success': False, 'message': 'Tipo de ativo inválido.'}), 400
        
        if not asset: return jsonify({'success': False, 'message': 'Ativo não encontrado.'}), 404
        # A verificação de posse agora é feita através do projeto
        if asset.project.user_id != current_user.id: return jsonify({'success': False, 'message': 'Não autorizado.'}), 403
        
        db.session.delete(asset)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Ativo apagado com sucesso.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erro no servidor: {e}'}), 500

@app.route('/character/<int:character_id>/copy_to/<int:project_id>', methods=['POST'])
@login_required
def copy_character(character_id, project_id):
    try:
        # Encontra o personagem original que queremos copiar
        char_to_copy = db.session.get(SavedCharacter, character_id)
        # Encontra o projeto para o qual queremos copiar
        dest_project = db.session.get(Project, project_id)

        # Validação: verifica se tudo existe e se o usuário é o dono de ambos
        if not char_to_copy or not dest_project:
            return jsonify({'success': False, 'message': 'Personagem ou projeto de destino não encontrado.'}), 404
        
        if char_to_copy.project.user_id != current_user.id or dest_project.user_id != current_user.id:
            return jsonify({'success': False, 'message': 'Não autorizado.'}), 403

        # Lógica da Cópia
        new_char = SavedCharacter(
            name=f"{char_to_copy.name} (Cópia)",
            concept=char_to_copy.concept,
            description=char_to_copy.description,
            project_id=dest_project.id  # Associa a cópia ao novo projeto
        )
        db.session.add(new_char)
        db.session.commit()
        
        return jsonify({'success': True, 'message': f'"{char_to_copy.name}" copiado para o projeto "{dest_project.name}" com sucesso!'})

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


# Em app.py

@app.route('/montar-prompt', methods=['POST'])
@login_required
def montar_prompt():
    data = request.json
    characters = data.get('characters', [])
    scenario = data.get('scenario', {})
    details = data.get('details', {})
    
    # <<< INÍCIO DA LÓGICA DO SOTAQUE >>>
    language = details.get('language', 'English')
    accent = details.get('accent')
    language_instruction = language  # Começa com o idioma base

    # Adiciona a instrução de sotaque apenas se for Português e um sotaque for escolhido
    if language == 'Português (Brasil)' and accent and accent not in ['Neutro Brasileiro', '']:
        language_instruction = f"Português (Brasil) com sotaque '{accent}'"
    # <<< FIM DA LÓGICA DO SOTAQUE >>>

    character_concepts = "\n".join([f"- Character Concept for '{c.get('name')}': {c.get('description')}" for c in characters])
    scenario_concept = f"- Scenario Concept for '{scenario.get('name')}': {scenario.get('description')}"
    
    dialogue_lines_pt_br = []
    if details.get('dialogues'):
      for d in details.get('dialogues', []):
          char_name = next((c['name'] for c in characters if str(c['id']) == str(d.get('charId'))), "Character")
          dialogue_lines_pt_br.append(f"- {char_name}: \"{d.get('text')}\"")

    final_assembly_instruction = f"""
    You are a professional prompt engineer. Your only task is to generate a complete video prompt by precisely following the structure and rules below.
    
    **USER'S RAW DATA:**
    Action Context: "{details.get('action_context')}"
    Visual Style: "{details.get('visual_style')}"
    Camera Style: "{details.get('camera_style')}"
    Character Concepts:
      {character_concepts}
    Scenario Concept:
      {scenario_concept}
    Dialogue Sequence (to be translated to {language_instruction}):
      {"\n".join(dialogue_lines_pt_br) if dialogue_lines_pt_br else "No dialogue provided."}

    **GENERATION TASK - Follow this structure EXACTLY:**

    Prompt Title:
    [Generate a 1-3 word title in ENGLISH based on the Action Context]
    Initial AI Instructions:
    Visual Style: {details.get('visual_style')} Camera Style: {details.get('camera_style')} Language: {language_instruction} with perfect lip-sync.
    {"\n---\n\n".join([f'''👤 Character Profile: {c.get('name')}
    <char_{c.get('name').replace(' ', '_')}_start>
    [Expand the character concept to '{c.get('name')}' Gender: [Character's gender] Age: [Character's age] Ethnicity: [Character's ethnicity] Skin Tone: [Detailed skin color and undertone] Body: [Height, build (e.g., ectomorph), posture, and proportions] Face: [Overall shape, cheekbones, jawline, and chin details] Eyes: [Color, shape, eyebrows, and eyelashes] Nose: [Bridge, nostrils, and tip shape] Mouth: [Lip shape, size, and notable details like Cupid's bow] Hair: [Color, texture, curl type (e.g., 4B), length, and default style] Facial Hair: [Describe beard/mustache, if any] Unique Features: [List all distinctive scars, moles, tattoos, piercings, etc.]
    </char_{c.get('name').replace(' ', '_')}_end>
    Attire: [Describe what this character is wearing in this specific scene.] Posture: [Describe their posture in this scene (e.g., leaning forward, arms crossed).] Facial Expression: [Describe their facial expression in this scene (e.g., a faint smile, a worried frown).]
''' for c in characters])}
    Scene Breakdown
    Scene 01 (0.0s – 4.0s):
    Action: [Describe what the characters are doing, ensuring the action is directly inspired by the "Action Context".]
    Dialogue ({language_instruction}): [Translate the first dialogue line and attribute it in the format: Character Name says "Translated text.".]
    Camera: [Describe a camera movement and framing for this scene.]
    Cinematography: [Describe a technical detail for this scene.]
    Scene 02 (4.0s – 8.0s):
    Action: [Describe the continuing action for this scene.]
    Dialogue ({language_instruction}): [Translate the second dialogue line and attribute it.]
    Camera: [Describe a camera movement and framing for this scene.]
    Cinematography: [Describe a technical detail for this scene.]
    Scene Setup:
    <scen_{scenario.get('name', 'default').replace(' ', '_')}_start>
    Location: [Expand the Scenario Concept into a detailed description of the location.] Lighting: [Describe the lighting of the scene.] Atmosphere: [Describe the atmosphere, sounds, and smells.]
    </scen_{scenario.get('name', 'default').replace(' ', '_')}_end>
    Instructions Final for IA:
    Visual Style: {details.get('visual_style')} Color Grading: [Describe a color grading style.] Duration: 8 seconds. Language: {language_instruction} with perfect lip-sync. Audio: [Describe the audio mix.] Output: No watermarks, no subtitles.
    """
    final_prompt = generate_ia_content(final_assembly_instruction)
    return jsonify({'prompt': final_prompt})


@app.route('/save_from_prompt', methods=['POST'])
@login_required
def save_from_prompt():
    # Esta rota agora pega o projeto da sessão
    project_id = session.get('current_project_id')
    if not project_id:
        return jsonify({'success': False, 'message': 'Nenhum projeto ativo na sessão. Inicie a criação a partir da biblioteca.'}), 400

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
            exists = SavedCharacter.query.filter_by(project_id=project_id, name=component_name).first()
            if exists:
                return jsonify({'success': True, 'message': f'"{component_name}" já estava salvo neste projeto.'})
            
            new_char = SavedCharacter(name=component_name, concept=description, description=description, project_id=project_id)
            db.session.add(new_char)

        elif component_type == 'scenario':
            exists = SavedScenario.query.filter_by(project_id=project_id, name=component_name).first()
            if exists:
                return jsonify({'success': True, 'message': f'"{component_name}" já estava salvo neste projeto.'})

            new_scen = SavedScenario(name=component_name, concept=description, description=description, project_id=project_id)
            db.session.add(new_scen)
        
        db.session.commit()
        return jsonify({'success': True, 'message': f'"{component_name}" salvo com sucesso no projeto "{session.get("current_project_name", "")}"!'})

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

# Coloque este código no final do seu arquivo app.py

@app.cli.command("seed-default-project")
def seed_default_project_command():
    """Cria um Projeto Padrão para cada usuário e associa componentes órfãos."""
    try:
        users = User.query.all()
        if not users:
            print("Nenhum usuário encontrado para criar projetos padrão.")
            return

        for user in users:
            # Verifica se o usuário já tem um projeto padrão
            default_project = Project.query.filter_by(user_id=user.id, name="Projeto Padrão").first()
            if not default_project:
                print(f"Criando 'Projeto Padrão' para o usuário {user.email}...")
                default_project = Project(name="Projeto Padrão", user_id=user.id)
                db.session.add(default_project)
                db.session.commit() # Salva para obter o ID do projeto

            # Encontra personagens e cenários antigos que pertenciam diretamente ao usuário
            # Esta parte assume que a migração anterior ainda não removeu a coluna user_id.
            # Se a coluna user_id já foi removida e substituída por project_id (nulo), ajustamos a lógica.

            # Lógica correta para o estado atual (project_id é nulo)
            print(f"Associando componentes órfãos ao projeto padrão do usuário {user.email}...")

            # Encontra os personagens e cenários do usuário que estão sem projeto
            # A forma de fazer isso depende de como os dados estavam estruturados.
            # Vamos assumir que você precisa de uma forma de ligar os personagens antigos aos usuários.
            # A melhor forma é fazer isso antes da migração, mas podemos corrigir agora.

            # Como não temos mais a ligação user_id, vamos associar todos os componentes sem projeto
            # ao projeto padrão do PRIMEIRO usuário. É uma simplificação.

            # Associa todos os personagens sem projeto ao projeto padrão deste usuário
            chars_to_update = SavedCharacter.query.filter_by(project_id=None).all()
            for char in chars_to_update:
                char.project_id = default_project.id

            # Associa todos os cenários sem projeto ao projeto padrão deste usuário
            scens_to_update = SavedScenario.query.filter_by(project_id=None).all()
            for scen in scens_to_update:
                scen.project_id = default_project.id

            db.session.commit()
            print(f"Componentes do usuário {user.email} foram associados.")

        print("Processo de associação concluído.")
    except Exception as e:
        db.session.rollback()
        print(f"Ocorreu um erro: {e}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)