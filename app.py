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
        character_concept_pt = data.get('character')
        dialogue_text_pt = data.get('dialogue')
        language_text = data.get('language')
        use_slang_text = data.get('slang')
        accent_text = data.get('accent')
        location_concept_pt = data.get('location')
        date_text = data.get('date')
        camera_style_text = data.get('camera_style')
        visual_style_text = data.get('visual_style')
        atmosphere_text = data.get('atmosphere')

        required_fields = [character_concept_pt, dialogue_text_pt, language_text, location_concept_pt, accent_text]
        if not all(required_fields):
            return jsonify({'error': 'Os campos de personagem, fala, idioma, local e sotaque são obrigatórios.'}), 400

        # --- MUDANÇA 1: Lógica para especificar o idioma no backend ---
        # Se o idioma recebido do frontend for "Português", ele será trocado por "Brazilian Portuguese" antes de ser enviado para a IA.
        if language_text == 'Português':
            language_text = 'Brazilian Portuguese'
        
        # --- Montagem da Instrução para a IA (VERSÃO FINAL) ---
        instruction = f"""
        You are an expert prompt engineer for AI video generators. Your mission is to convert user concepts into a structured, HYPER-DETAILED, and evocative prompt in ENGLISH.

        **1. CORE IDEAS FROM USER:**
        - Character Concept (in Portuguese): "{character_concept_pt}"
        - Location Concept (in Portuguese): "{location_concept_pt}"
        - Original Dialogue: "{dialogue_text_pt}"
        - Dialogue Language: "{language_text}"
        - Use Slang: "{use_slang_text}"
        - Character's Accent: "{accent_text}"
        - Desired Atmosphere: "{atmosphere_text}"
        - Date of Scene: "{date_text}"
        - Camera Style: "{camera_style_text}"
        - Visual Style: "{visual_style_text}"

        **2. YOUR TASK - VERY IMPORTANT RULES:**
        - Create a final prompt in ENGLISH, structured with the labels below.
        - Descriptions for Character and Scene must be MASSIVELY EXPANDED AND EXTREMELY DETAILED.
        - The Character's description MUST be heavily influenced by their specified Accent ('{accent_text}').

        - **STRICT DIALOGUE RULES (Follow Precisely):**
          - **IF 'Use Slang' is 'Sim':** You MUST rephrase the 'Original Dialogue' ('{dialogue_text_pt}') to include authentic slang and colloquialisms that match the specified 'Accent' ('{accent_text}') and 'Dialogue Language' ('{language_text}').
          - **IF 'Use Slang' is 'Não':** You MUST use the 'Original Dialogue' ('{dialogue_text_pt}') VERBATIM. Do not change a single word.
          - The final prompt MUST explicitly state the language and accent, and then the dialogue. The format inside the 'Action' section must be: `...speaking in {language_text} with a {accent_text} accent, and says: "[final dialogue text here]"`.

        - The final output MUST follow this exact format:

        **Visuals:** [Combine Visual Style and Atmosphere here]
        **Scene:** [A hyper-detailed description of the location]
        **Character:** [A hyper-detailed description of the character, deeply informed by their accent]
        **Action:** [A detailed description of the character's physical action, followed by the explicit language, accent, and the final dialogue as per the rules above]
        
        # --- MUDANÇA 2: Adicionar comandos técnicos fixos ---
        **Technical:** [Combine Camera Style and other technical commands, and you MUST append the following keywords at the end: ', no captions, clean video, no music.']

        Now, generate the final, structured, hyper-detailed prompt based on all these rules.
        """

        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(instruction)

        return jsonify({'prompt': response.text})

    except Exception as e:
        print(f"Erro detalhado no servidor: {e}")
        return jsonify({'error': 'Ocorreu um erro no servidor ao gerar o prompt.'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)