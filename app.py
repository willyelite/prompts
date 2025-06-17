import os
import google.generativeai as genai
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("A variável de ambiente GEMINI_API_KEY não foi encontrada.")
genai.configure(api_key=api_key)

app = Flask(__name__)

# --- CONFIGURAÇÃO DO POSTGRESQL (Sua lógica, perfeita) ---
db_url = os.getenv('DATABASE_URL')
if not db_url:
    raise ValueError("A variável de ambiente DATABASE_URL não foi encontrada.")

if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
# --- FIM DA CONFIGURAÇÃO ---


# --- MODELO DO BANCO DE DADOS (Sua lógica, perfeita) ---
class Counter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hits = db.Column(db.Integer, default=0)

# Cria a tabela no banco de dados se ela não existir
with app.app_context():
    db.create_all()


@app.route('/')
def index():
    # Procura pelo contador no banco de dados (deve haver apenas uma linha com id=1)
    hit_counter = db.session.get(Counter, 1)

    if hit_counter is None:
        # Se não existir, cria o contador começando em 1
        hit_counter = Counter(id=1, hits=1)
        db.session.add(hit_counter)
    else:
        # Se já existir, apenas incrementa
        hit_counter.hits += 1

    # Salva a mudança no banco de dados
    db.session.commit()

    # Passa o número de hits para o template
    return render_template('index.html', hits=hit_counter.hits)


# --- SUA FUNÇÃO DE GERAR PROMPT (AGORA FORA DA FUNÇÃO INDEX) ---
@app.route('/generate-prompt', methods=['POST'])
def generate_prompt():
    try:
        data = request.json
        
        # Coleta de dados
        character_concept_pt = data.get('character')
        dialogue_text_pt = data.get('dialogue')
        use_slang_text = data.get('slang')
        accent_text = data.get('accent')
        location_concept_pt = data.get('location')
        date_text = data.get('date')
        camera_style_text = data.get('camera_style')
        visual_style_text = data.get('visual_style')
        atmosphere_text = data.get('atmosphere')
        character_count = data.get('character_count', '1')
        character2_concept_pt = data.get('character2')
        dialogue2_text_pt = data.get('dialogue2')

        # Validação
        if not all([character_concept_pt, dialogue_text_pt, location_concept_pt, accent_text]):
            return jsonify({'error': 'Os campos de personagem 1, fala 1, local e sotaque são obrigatórios.'}), 400
        if character_count == '2' and not all([character2_concept_pt, dialogue2_text_pt]):
            return jsonify({'error': 'Os campos de descrição e fala para o Personagem 2 são obrigatórios.'}), 400

        # --- Montagem da Instrução para a IA ---
        
        character_2_block = ""
        if character_count == '2':
            character_2_block = f"""
        **CHARACTER 2 DATA:**
        - Concept: "{character2_concept_pt}"
        - Dialogue: "{dialogue2_text_pt}"
        """

        cctv_instruction = ""
        if "CCTV" in camera_style_text:
            cctv_instruction = "For the Scene description, you MUST describe the shot as being 'from a high corner of the room, slightly tilted down, creating a sense of distant, detached surveillance'."

        instruction = f"""
        You are an expert prompt engineer. Your mission is to assemble a hyper-detailed prompt based on the user's data, following a strict structural recipe.

        **1. INGREDIENTS (Source of Truth):**
        
        **SCENE INGREDIENTS:**
        - Location Concept: "{location_concept_pt}"
        - Atmosphere: "{atmosphere_text}"
        - Date: "{date_text}"
        - Camera Style Keywords: "{camera_style_text}"
        - Visual Style Keywords: "{visual_style_text}"

        **DIALOGUE RULES:**
        - Use Slang: "{use_slang_text}"
        - Shared Accent: "{accent_text}"
        
        **CHARACTER 1 DATA:**
        - Concept: "{character_concept_pt}"
        - Dialogue: "{dialogue_text_pt}"
        {character_2_block}

        **2. ASSEMBLY RECIPE (Follow Step-by-Step):**

        You WILL now generate the final prompt in ENGLISH using the 5 labels below.

        - **For 'Visuals:':** Creatively combine 'Atmosphere' and 'Visual Style Keywords'. DO NOT repeat these keywords later.
        - **For 'Scene:':** Translate and expand the 'Location Concept' into a hyper-detailed paragraph. {cctv_instruction}
        - **For 'Character 1:' and 'Character 2:':** For EACH character, you MUST generate a new block with TWO sub-headings: '- Description:' and '- Dialogue:'.
            - Under '- Description:', you MUST apply the 'MANDATORY CHARACTER DETAIL CHECKLIST' to the character's 'Concept'.
            - Under '- Dialogue:', you MUST place the character's corresponding 'Dialogue'. If 'Use Slang' is 'Sim', rephrase it with the specified accent. If 'Não', use it VERBATIM. This structure is non-negotiable.
        - **For 'Action:':** Describe ONLY the physical actions and interactions between characters. DO NOT include the dialogue text here, as it is already defined under each character.
        - **For 'Technical:':** List the 'Camera Style Keywords' and append the standard commands: ', no captions, clean video, no music.'

        **MANDATORY CHARACTER DETAIL CHECKLIST (Apply to EACH character's Description):**
        Invent and include: Age and Ethnicity, Facial Structure, Eyes, Hair, Skin Details, Physique, Clothing, and Defining Expression.

        **3. FINAL OUTPUT (Generate Now):**
        """
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(instruction)
        return jsonify({'prompt': response.text})
    except Exception as e:
        print(f"Erro detalhado no servidor: {e}")
        return jsonify({'error': 'Ocorreu um erro no servidor ao gerar o prompt.'}), 500

if __name__ == '__main__':
    # Mudado a porta para 5000 para evitar conflitos locais. Render ignora isso.
    app.run(host='0.0.0.0', port=5000, debug=True)