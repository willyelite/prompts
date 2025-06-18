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
        p1_desc = data.get('character1_desc')
        p1_dialogue = data.get('dialogue1')
        p1_language = process_language(data.get('language1'))
        
        p2_desc = data.get('character2_desc')
        p2_dialogue = data.get('dialogue2')
        p2_language = process_language(data.get('language2'))
        
        location_concept_pt = data.get('location')
        date_text = data.get('date')
        camera_style_text = data.get('camera_style')
        visual_style_text = data.get('visual_style')
        atmosphere_text = data.get('atmosphere')
        accent_text = data.get('accent')
        slang_text = data.get('slang')
        
        is_two_character_scene = bool(p2_desc and p2_dialogue)

        # Validação
        if not all([p1_desc, p1_dialogue]):
            return jsonify({'error': 'A descrição e a fala do Personagem 1 são obrigatórias.'}), 400
        if is_two_character_scene and not all([p2_desc, p2_dialogue]):
            return jsonify({'error': 'Os campos de descrição e fala para o Personagem 2 são obrigatórios.'}), 400

        concept_instruction_text = "You MUST treat the 'Creative Concept' as the absolute core of the character. If the concept is an iconic character (like a superhero), your description MUST include their recognizable costume and attributes faithfully. Your task is to build the details from the 'MANDATORY CHECKLIST' AROUND this core identity, not to replace it."
        dialogue_instruction_text = ""
        if slang_text == 'Sim':
            dialogue_instruction_text = "Rephrase the 'Original Dialogue' with authentic slang and colloquialisms that match the specified 'Accent'."
        else:
            dialogue_instruction_text = "Use the 'Original Dialogue' VERBATIM. This is a strict command: you must output the exact, character-for-character string provided without any changes, corrections, or punctuation additions."

        instruction = ""
        if is_two_character_scene:
            instruction = f"""
            You are a creative prompt engineer for AI video generators, creating a dynamic two-character dialogue scene.
            **1. CORE CONCEPTS & RULES:**
            - General Style: "{visual_style_text}", "{camera_style_text}", Date: "{date_text}"
            - Scene: Location Idea: "{location_concept_pt}", Atmosphere: "{atmosphere_text}"
            - Character Interpretation Rule: {concept_instruction_text}
            - Dialogue Interpretation Rule: {dialogue_instruction_text}
            
            **2. CHARACTER 1 DATA:**
            - Creative Concept: "{p1_desc}"
            - Original Dialogue: "{p1_dialogue}" spoken in {p1_language} with a '{accent_text}' accent.

            **3. CHARACTER 2 DATA:**
            - Creative Concept: "{p2_desc}"
            - Original Dialogue: "{p2_dialogue}" spoken in {p2_language} with a '{accent_text}' accent.

            **4. YOUR TASK (The Recipe):**
            - Create the final prompt in ENGLISH, structured with the labels below.
            - For the 'Characters' section: You MUST generate two separate, detailed paragraphs, one starting with the literal label '**Character 1:**' and the other with '**Character 2:**'.
            - For each character block: You MUST create TWO sub-headings: '- Description:' and '- Dialogue:'. Under '- Description:', apply the 'MANDATORY CHARACTER DETAIL CHECKLIST'. Under '- Dialogue:', you MUST apply the 'Dialogue Interpretation Rule' to that character's 'Original Dialogue'.
            - In the 'Scene Breakdown / Action' section, describe the interaction, but DO NOT repeat the dialogue text.

            **5. FINAL PROMPT STRUCTURE:**
            **Visuals:** ...
            **Scene:** ...
            **Characters:** ...
            **Scene Breakdown / Action:** ...
            **Technical:** [For the 'Technical:' section, you MUST list the 'Camera Style Keywords' and 'Date', and then you MUST ALWAYS append the exact phrase: ', no captions, clean video, no music.']
            
            **MANDATORY CHARACTER DETAIL CHECKLIST (Apply to EACH character's Description):**
            Invent: Age and Ethnicity, Facial Structure, Eyes, Hair, Skin Details, Physique, Clothing, and Defining Expression.
            """
        else:
            instruction = f"""
            You are a creative prompt engineer for AI video generators.
            Your mission is to use the user's high-level concept to generate a HYPER-DETAILED prompt in ENGLISH.

            **1. CORE CONCEPTS & RULES:**
            - Character's Creative Concept: "{p1_desc}"
            - Original Dialogue: "{p1_dialogue}" spoken in {p1_language} with a '{accent_text}' accent.
            - Scene: Location: "{location_concept_pt}", Atmosphere: "{atmosphere_text}"
            - General Style: "{visual_style_text}", "{camera_style_text}", Date: "{date_text}"
            - Character Interpretation Rule: {concept_instruction_text}
            - Dialogue Interpretation Rule: {dialogue_instruction_text}
            
            **2. YOUR TASK (The Recipe):**
            - Create the final prompt structured with the labels below.
            - In the 'Character:' section, create TWO sub-headings: '- Description:' and '- Dialogue:'.
            - For the '- Dialogue:' sub-heading, you MUST apply the 'Dialogue Interpretation Rule' to the 'Original Dialogue'.

            **3. FINAL PROMPT STRUCTURE:**
            **Visuals:** ...
            **Scene:** ...
            **Character:** ...
            **Action:** ...
            **Technical:** [For the 'Technical:' section, you MUST list the 'Camera Style Keywords' and 'Date', and then you MUST ALWAYS append the exact phrase: ', no captions, clean video, no music.']

            **MANDATORY CHARACTER DETAIL CHECKLIST (Apply to the character's Description):**
            Invent: Age and Ethnicity, Facial Structure, Eyes, Hair, Skin Details, Physique, Clothing, and Defining Expression.
            """
        
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(instruction)
        return jsonify({'prompt': response.text})
    except Exception as e:
        print(f"Erro detalhado no servidor: {e}")
        return jsonify({'error': 'Ocorreu um erro no servidor ao gerar o prompt.'}), 500

@app.route('/save-character', methods=['POST'])
def save_character():
    try:
        data = request.json
        name = data.get('name')
        description = data.get('description')
        if not all([name, description]):
            return jsonify({'success': False, 'error': 'Dados incompletos.'}), 400
        existing_char = SavedCharacter.query.filter_by(name=name).first()
        if existing_char:
            return jsonify({'success': False, 'error': f'Já existe um personagem chamado "{name}".'}), 400
        new_char = SavedCharacter(name=name, description=description)
        db.session.add(new_char)
        db.session.commit()
        return jsonify({'success': True, 'message': f'Personagem "{name}" salvo com sucesso!'})
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao salvar personagem: {e}")
        return jsonify({'success': False, 'error': 'Erro interno do servidor.'}), 500

@app.route('/characters', methods=['GET'])
def get_characters():
    try:
        characters = SavedCharacter.query.order_by(SavedCharacter.name).all()
        character_names = [char.name for char in characters]
        return jsonify(character_names)
    except Exception as e:
        print(f"Erro ao buscar personagens: {e}")
        return jsonify([]), 500

@app.route('/character/<name>', methods=['GET'])
def get_character_details(name):
    try:
        character = SavedCharacter.query.filter_by(name=escape(name)).first()
        if character:
            return jsonify({'name': character.name, 'description': character.description})
        else:
            return jsonify({'error': 'Personagem não encontrado.'}), 404
    except Exception as e:
        print(f"Erro ao buscar detalhes do personagem: {e}")
        return jsonify({'error': 'Erro interno do servidor.'}), 500

@app.route('/character/<name>', methods=['DELETE'])
def delete_character(name):
    try:
        character = SavedCharacter.query.filter_by(name=escape(name)).first()
        if character:
            db.session.delete(character)
            db.session.commit()
            return jsonify({'success': True, 'message': f'Personagem "{name}" apagado com sucesso.'})
        else:
            return jsonify({'success': False, 'error': 'Personagem não encontrado.'}), 404
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao apagar personagem: {e}")
        return jsonify({'success': False, 'error': 'Erro interno do servidor.'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)