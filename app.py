import os
import google.generativeai as genai
from flask import Flask, render_template, request, jsonify
from markupsafe import escape
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("A variável de ambiente GEMINI_API_KEY não foi encontrada.")
genai.configure(api_key=api_key)

app = Flask(__name__)

# --- CONFIGURAÇÃO DO POSTGRESQL ---
db_url = os.getenv('DATABASE_URL')
if not db_url:
    raise ValueError("A variável de ambiente DATABASE_URL não foi encontrada.")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- MODELOS DO BANCO DE DADOS ---
class Counter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hits = db.Column(db.Integer, default=0)

class SavedCharacter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)

with app.app_context():
    db.create_all()

# --- ROTAS DA APLICAÇÃO ---
@app.route('/')
def index():
    hit_counter = db.session.get(Counter, 1)
    if hit_counter is None:
        hit_counter = Counter(id=1, hits=1)
        db.session.add(hit_counter)
    else:
        hit_counter.hits += 1
    db.session.commit()
    return render_template('index.html', hits=hit_counter.hits)

@app.route('/generate-prompt', methods=['POST'])
def generate_prompt():
    try:
        data = request.json
        
        def process_language(lang):
            return 'Brazilian Portuguese' if lang == 'Português' else lang

        # Coleta de dados
        # Gerais
        location_concept_pt = data.get('location')
        date_text = data.get('date')
        camera_style_text = data.get('camera_style')
        visual_style_text = data.get('visual_style')
        atmosphere_text = data.get('atmosphere')
        accent_text = data.get('accent')
        slang_text = data.get('slang')
        # Personagem 1
        p1_desc = data.get('character1_desc')
        p1_dialogue = data.get('dialogue1')
        p1_language = process_language(data.get('language1')) # Lendo idioma 1
        # Personagem 2
        p2_desc = data.get('character2_desc')
        p2_dialogue = data.get('dialogue2')
        p2_language = process_language(data.get('language2')) # Lendo idioma 2
        
        is_two_character_scene = bool(p2_desc and p2_dialogue)

        # Validação
        if not all([p1_desc, p1_dialogue]):
            return jsonify({'error': 'A descrição e a fala do Personagem 1 são obrigatórias.'}), 400
        if is_two_character_scene and not all([p2_desc, p2_dialogue]):
            return jsonify({'error': 'Os campos de descrição e fala para o Personagem 2 são obrigatórios.'}), 400

        # Montagem da Instrução para a IA
        instruction = ""
        if is_two_character_scene:
            instruction = f"""
            You are an expert prompt engineer for AI video generators, creating a dynamic two-character dialogue scene.
            **1. GENERAL SCENE PARAMETERS:**
            - Location: "{location_concept_pt}", Atmosphere: "{atmosphere_text}", Date: "{date_text}"
            - Visual Style: "{visual_style_text}", Camera Style: "{camera_style_text}"

            **2. CHARACTER 1 DATA:**
            - Concept: "{p1_desc}", Accent: "{accent_text}", Use Slang: "{slang_text}"
            - Dialogue: "{p1_dialogue}" in {p1_language}

            **3. CHARACTER 2 DATA:**
            - Concept: "{p2_desc}", Accent: "{accent_text}", Use Slang: "{slang_text}"
            - Dialogue: "{p2_dialogue}" in {p2_language}

            **4. YOUR TASK - VERY IMPORTANT RULES:**
            - Create a final prompt in ENGLISH, structured with the labels below.
            - 'Characters' section must contain hyper-detailed descriptions for BOTH characters, labeled "Character 1" and "Character 2", influenced by their concepts and accents.
            - **STRICT DIALOGUE RULES:** For each character, check their 'Use Slang' parameter (note: this is a general rule for both). If 'Sim', rephrase their dialogue with authentic slang. If 'Não', use their dialogue VERBATIM.
            - In the 'Scene Breakdown' section, describe the interaction. When they speak, you MUST use the explicit format: `Character 1 speaks in {p1_language} with a {accent_text} accent: "[Final dialogue for C1]"`, followed by `Character 2 replies in {p2_language} with a {accent_text} accent: "[Final dialogue for C2]"`.

            **5. FINAL OUTPUT FORMAT:**
            **Visuals:** [Combine Visual Style and Atmosphere]
            **Scene:** [Hyper-detailed description of the location]
            **Characters:** [Detailed paragraph for Character 1, then a detailed paragraph for Character 2]
            **Scene Breakdown / Action:** [Description of the scene unfolding, including the dialogue exchange in the specified format.]
            **Technical:** [{camera_style_text}, Date: {date_text}, no captions, clean video, no music.]
            """
        else:
            instruction = f"""
            You are an expert prompt engineer for AI video generators. Your mission is to convert the user's concepts for a single character into a structured, HYPER-DETAILED prompt in ENGLISH.
            **1. CORE IDEAS FROM USER:**
            - Character Concept: "{p1_desc}", Accent: "{accent_text}", Use Slang: "{slang_text}"
            - Location Concept: "{location_concept_pt}"
            - Original Dialogue: "{p1_dialogue}" in {p1_language}
            - Atmosphere: "{atmosphere_text}"
            - Date: "{date_text}", Camera Style: "{camera_style_text}", Visual Style: "{visual_style_text}"

            **2. YOUR TASK:**
            - Create a final prompt structured with the labels below.
            - **DIALOGUE RULE:** If 'Use Slang' is 'Sim', rephrase the dialogue with slang. If 'Não', use it VERBATIM.
            - The 'Action' section must use the format: `...speaking in {p1_language} with a {accent_text} accent, and says: "[final dialogue text here]"`.

            **3. FINAL OUTPUT FORMAT:**
            **Visuals:** [Combine Visual Style and Atmosphere]
            **Scene:** [Hyper-detailed description of the location]
            **Character:** [Hyper-detailed description of the character]
            **Action:** [Detailed description of the character's action and their dialogue]
            **Technical:** [{camera_style_text}, Date: {date_text}, no captions, clean video, no music.]
            """
        
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(instruction)
        return jsonify({'prompt': response.text})
    except Exception as e:
        print(f"Erro detalhado no servidor: {e}")
        return jsonify({'error': 'Ocorreu um erro no servidor ao gerar o prompt.'}), 500

# Suas outras rotas (/save-character, /characters, /character/<name>, etc.) continuam aqui sem alterações

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)