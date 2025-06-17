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
        # Coletando todos os dados, incluindo os novos
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

        # Validação mais completa
        required_fields = [character_concept_pt, dialogue_text_pt, language_text, location_concept_pt, accent_text]
        if not all(required_fields):
            return jsonify({'error': 'Os campos de personagem, fala, idioma, local e sotaque são obrigatórios.'}), 400

        # --- Montagem da Instrução para a IA (VERSÃO COM MAIS NUANCES) ---
        instruction = f"""
        You are an expert prompt engineer for AI video generators. Your mission is to convert user concepts into a structured, HYPER-DETAILED, and evocative prompt in ENGLISH.

        **1. CORE IDEAS FROM USER:**
        - Character Concept (in Portuguese): "{character_concept_pt}"
        - Location Concept (in Portuguese): "{location_concept_pt}"
        - Dialogue Line (to understand emotion): "{dialogue_text_pt}"
        - Dialogue Language: "{language_text}"
        - Desired Atmosphere: "{atmosphere_text}"
        - Use Slang: "{use_slang_text}"
        - Character's Accent: "{accent_text}"

        **2. TECHNICAL & STYLISTIC PARAMETERS:**
        - Date of Scene: "{date_text}"
        - Camera Style: "{camera_style_text}"
        - Visual Style: "{visual_style_text}"

        **3. YOUR TASK:**
        - Create a final prompt in ENGLISH, structured with the labels below.
        - Your descriptions must be MASSIVELY EXPANDED AND EXTREMELY DETAILED.
        - The Character's description, clothing, and mannerisms MUST be heavily influenced by their specified Accent ('{accent_text}'). Invent culturally and regionally appropriate details.
        - If 'Use Slang' is 'Sim', the character's described action and expression should have a more informal, colloquial, and street-smart feel. If 'Não', they should be more standard or formal.
        - DO NOT include the verbatim dialogue. Instead, describe the CHARACTER'S ACTION AND EXPRESSION as they speak, reflecting the emotion, language, and accent.
        - The final output MUST follow this exact format:

        **Visuals:** [Combine Visual Style and Atmosphere here]
        **Scene:** [A hyper-detailed description of the location]
        **Character:** [A hyper-detailed description of the character, deeply informed by their accent and slang preference]
        **Action:** [A detailed description of the character's action, reflecting the emotion of their dialogue, their accent, and slang preference]
        **Technical:** [Combine Camera Style and other technical commands]

        **4. MANDATORY CHARACTER DETAIL CHECKLIST (Invent details for ALL, guided by the accent):**
        - **Age and Ethnicity:** Be specific.
        - **Facial Structure & Expression:** Jawline, cheekbones, and a defining expression that matches their accent/persona.
        - **Eyes:** Color, shape, expression.
        - **Hair:** Color, style, texture, condition.
        - **Skin Details:** Complexion, texture, scars, marks, etc.
        - **Physique / Body Type:** Posture and build that align with the persona.
        - **Clothing:** Describe every item, ensuring the style is authentic to the character's accent and culture.
        - **Defining Mannerism:** A characteristic gesture or tic heavily influenced by their accent ('{accent_text}').

        Now, generate the final, structured, hyper-detailed prompt.
        """

        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(instruction)

        return jsonify({'prompt': response.text})

    except Exception as e:
        print(f"Erro detalhado no servidor: {e}")
        return jsonify({'error': 'Ocorreu um erro no servidor ao gerar o prompt.'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)