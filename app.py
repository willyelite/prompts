import os
import google.generativeai as genai
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("A variável de ambiente GEMINI_API_KEY não foi encontrada.")
genai.configure(api_key=api_key)

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

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
        
        # Bloco de informações do Personagem 2 (só é adicionado se ele existir)
        character_2_block = ""
        if character_count == '2':
            character_2_block = f"""
        **CHARACTER 2 DATA:**
        - Concept (in Portuguese): "{character2_concept_pt}"
        - Dialogue (in Portuguese): "{dialogue2_text_pt}"
        """

        # A instrução principal agora agrupa os dados por personagem
        instruction = f"""
        You are an expert prompt engineer for AI video generators, specialized in creating dynamic scenes.

        **1. SCENE BRIEF:**
        - General Location Concept (in Portuguese): "{location_concept_pt}"
        - Shared Accent for all Characters: "{accent_text}"
        - Use Slang in Dialogue: "{use_slang_text}"
        - Desired Atmosphere: "{atmosphere_text}"
        - Date of Scene: "{date_text}"
        - Camera Style: "{camera_style_text}"
        - Visual Style: "{visual_style_text}"

        **2. CHARACTER DATA (Unambiguous Grouping):**

        **CHARACTER 1 DATA:**
        - Concept (in Portuguese): "{character_concept_pt}"
        - Dialogue (in Portuguese): "{dialogue_text_pt}"
        {character_2_block}

        **3. YOUR TASK - VERY IMPORTANT RULES:**
        - Create a final prompt in ENGLISH, strictly following the output format below.
        - Translate and MASSIVELY EXPAND upon all Portuguese concepts into hyper-detailed English descriptions.
        - For EVERY character provided, you MUST apply the MANDATORY CHARACTER DETAIL CHECKLIST.

        # <<< AQUI ESTÁ A MUDANÇA PRINCIPAL PARA CORRIGIR O BUG DAS GÍRIAS >>>
        - **STRICT DIALOGUE RULES (Your most important task - Follow with zero deviation):**
          - **IF 'Use Slang' is 'Não':** You are FORBIDDEN from altering the original dialogue. You MUST transfer the user's provided text VERBATIM, exactly as written. Any modification is a failure.
          - **IF 'Use Slang' is 'Sim':** You MUST creatively rewrite and rephrase the dialogue for ALL characters to include authentic slang and colloquialisms that match the specified '{accent_text}'.
        
        **4. MANDATORY CHARACTER DETAIL CHECKLIST (Apply to EACH character individually):**
        Invent and include specific details for ALL of the following: Age and Ethnicity, Facial Structure, Eyes, Hair, Skin Details, Physique, Clothing, and Defining Expression.

        **5. OUTPUT FORMAT (Use this exact structure):**

        **Visuals:** [Combine Visual Style and Atmosphere here. Be descriptive.]
        **Scene:** [A hyper-detailed description of the location.]
        **Character 1:** [A hyper-detailed description of Character 1 from the checklist.]
        **Character 2:** [IF Character 2 exists, a hyper-detailed description of Character 2 from the checklist. Omit this line if there is only one character.]
        **Action:** [A detailed description of the character(s) physical actions and their dialogue exchange. Ensure Character 1 speaks Character 1's dialogue, and Character 2 speaks Character 2's dialogue. The dialogue itself must be in Brazilian Portuguese.]
        **Technical:** [Combine Camera Style and other technical commands, and you MUST append: ', no captions, clean video, no music.']

        Now, generate the final, structured, hyper-detailed prompt.
        """

        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(instruction)

        return jsonify({'prompt': response.text})

    except Exception as e:
        print(f"Erro detalhado no servidor: {e}")
        return jsonify({'error': 'Ocorreu um erro no servidor ao gerar o prompt.'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)