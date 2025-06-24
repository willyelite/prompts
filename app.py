import os
import google.generativeai as genai
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy

# --- CONFIGURAÇÃO INICIAL ---
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("A variável de ambiente GEMINI_API_KEY não foi encontrada.")
genai.configure(api_key=api_key)

app = Flask(__name__)

# --- CONFIGURAÇÃO DO BANCO DE DADOS POSTGRESQL ---
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
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=False)

with app.app_context():
    db.create_all()

# --- FUNÇÃO HELPER PARA CHAMAR A IA ---
def generate_ia_content(instruction):
    model = genai.GenerativeModel('gemini-1.5-flash')
    try:
        response = model.generate_content(instruction)
        return response.text
    except Exception as e:
        print(f"Erro na chamada da API Gemini: {e}")
        return f"Erro na IA: {e}"

# --- ROTAS PRINCIPAIS ---
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
        
        # Coleta de dados do payload
        character_concept_pt = data.get('character1')
        dialogue_text_pt = data.get('dialogue1')
        location_concept_pt = data.get('location')
        scene_action_text = data.get('scene_action')
        use_slang_text = data.get('slang')
        accent_text = data.get('accent')
        language_text = data.get('language')
        character_count = data.get('character_count', '1')
        
        # --- PIPELINE DE GERAÇÃO ATÔMICA ---
        desc_instruction_1 = f"Generate a hyper-detailed character description in ENGLISH based on this concept: '{character_concept_pt}'. You MUST include details for: Age and Ethnicity, Facial Structure, Eyes, Hair, Skin Details, Physique, Clothing, and Defining Expression."
        desc_text_1 = generate_ia_content(desc_instruction_1)

        action_instruction_1 = f"The overall scene context is '{scene_action_text}'. Based on the character '{desc_text_1}' and their dialogue '{dialogue_text_pt}', describe in ENGLISH their specific physical action just before or while they speak."
        action_text_1 = generate_ia_content(action_instruction_1)

        if use_slang_text == 'Sim':
            slang_instruction_1 = f"Rephrase the following portuguese dialogue to include authentic slang for a '{accent_text}' accent, keeping the core meaning: '{dialogue_text_pt}'"
            dialogue_text_1 = generate_ia_content(slang_instruction_1)
        else:
            dialogue_text_1 = dialogue_text_pt

        desc_text_2, action_text_2, dialogue_text_2 = "", "", ""
        if character_count == '2':
            character2_concept_pt = data.get('character2')
            dialogue2_text_pt = data.get('dialogue2')
            
            desc_instruction_2 = f"Generate a hyper-detailed character description in ENGLISH based on this concept: '{character2_concept_pt}'. You MUST include details for: Age and Ethnicity, Facial Structure, Eyes, Hair, Skin Details, Physique, Clothing, and Defining Expression."
            desc_text_2 = generate_ia_content(desc_instruction_2)
            
            action_instruction_2 = f"The overall scene context is '{scene_action_text}'. A character just said '{dialogue_text_1}'. Now, another character described as '{desc_text_2}' is about to say '{dialogue2_text_pt}'. Describe in ENGLISH the second character's physical action and reaction."
            action_text_2 = generate_ia_content(action_instruction_2)

            if use_slang_text == 'Sim':
                slang_instruction_2 = f"Rephrase the following portuguese dialogue to include authentic slang for a '{accent_text}' accent, keeping the core meaning: '{dialogue2_text_pt}'"
                dialogue_text_2 = generate_ia_content(slang_instruction_2)
            else:
                dialogue_text_2 = dialogue2_text_pt
        
        visuals_instruction = f"Generate a descriptive sentence in ENGLISH for 'Visuals' by creatively combining these concepts: Atmosphere '{data.get('atmosphere')}' and Visual Style '{data.get('visual_style')}'."
        visuals_text = generate_ia_content(visuals_instruction)

        cctv_instruction = "For the Scene description, you MUST describe the shot as being 'from a high corner of the room, slightly tilted down, creating a sense of distant, detached surveillance'." if "CCTV" in data.get('camera_style', '') else ""
        scene_instruction = f"Generate a hyper-detailed paragraph in ENGLISH describing a scene. The concept is '{location_concept_pt}'. The date is {data.get('date')}. {cctv_instruction}"
        scene_text = generate_ia_content(scene_instruction)

        # --- MONTAGEM FINAL (FEITA PELO PYTHON) ---
        character_1_block = f"""Character 1:
- Description: {desc_text_1.strip()}
- Action: {action_text_1.strip()}
- Dialogue: "{dialogue_text_1.strip()}"
"""
        character_2_block = ""
        if character_count == '2':
            character_2_block = f"""
Character 2:
- Description: {desc_text_2.strip()}
- Action: {action_text_2.strip()}
- Dialogue: "{dialogue_text_2.strip()}"
"""
        final_prompt = f"""
Visuals: {visuals_text.strip()}

Scene: {scene_text.strip()}

{character_1_block.strip()}
{character_2_block.strip()}

Technical: {data.get('camera_style')}, no captions, clean video, no music.
"""
        # GERAÇÃO DO TÍTULO INTELIGENTE
        title_instruction = f"Read the following detailed scene prompt and summarize it in a short, human-readable title of no more than 6-8 words in Portuguese. Example: 'Detetive investiga cena do crime à noite'. Here is the prompt: {final_prompt}"
        title_text = generate_ia_content(title_instruction)

        return jsonify({'prompt': final_prompt.strip(), 'title': title_text.strip()})

    except Exception as e:
        print(f"Erro detalhado no servidor: {e}")
        return jsonify({'error': 'Ocorreu um erro no servidor ao gerar o prompt.'}), 500

# --- ROTAS DA BIBLIOTECA DE PERSONAGENS ---
@app.route('/save-character', methods=['POST'])
def save_character():
    data = request.json
    name = data.get('name')
    description = data.get('description')
    if not name or not description: return jsonify({'error': 'Nome e descrição são necessários.'}), 400
    if SavedCharacter.query.filter_by(name=name).first(): return jsonify({'error': f'Já existe um personagem salvo com o nome "{name}".'}), 400
    new_character = SavedCharacter(name=name, description=description)
    db.session.add(new_character)
    db.session.commit()
    return jsonify({'success': True, 'message': f'Personagem "{name}" salvo com sucesso!'})

@app.route('/characters', methods=['GET'])
def get_characters():
    characters = SavedCharacter.query.order_by(SavedCharacter.name).all()
    return jsonify([{'id': char.id, 'name': char.name} for char in characters])

@app.route('/character/<int:character_id>', methods=['GET'])
def get_character(character_id):
    character = db.session.get(SavedCharacter, character_id)
    return jsonify({'id': character.id, 'name': character.name, 'description': character.description}) if character else jsonify({'error': 'Personagem não encontrado.'}), 404

@app.route('/character/<int:character_id>', methods=['DELETE'])
def delete_character(character_id):
    character = db.session.get(SavedCharacter, character_id)
    if character:
        db.session.delete(character)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Personagem apagado com sucesso.'})
    return jsonify({'error': 'Personagem não encontrado.'}), 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)