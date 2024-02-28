from flask import Flask, request, render_template, send_file, after_this_request, make_response,session

import spacy
from spacy.matcher import Matcher
import pandas as pd
from PyPDF2 import PdfReader
import io
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Required for session management


# Load spaCy model
nlp = spacy.load('en_core_web_md')

# Assuming skills.jsonl is correctly placed in the data folder
skill_path = 'data/skills.jsonl'
ruler = nlp.add_pipe("entity_ruler", before="ner")
ruler.from_disk(skill_path)

# Function to preprocess text
def preprocessing(sentence):
    stopwords = list(spacy.lang.en.stop_words.STOP_WORDS)
    doc = nlp(sentence)
    clean_tokens = []
    for token in doc:
        if token.text not in stopwords and token.pos_ not in ['PUNCT', 'SYM', 'SPACE']:
            clean_tokens.append(token.lemma_.lower().strip())                
    return " ".join(clean_tokens)

# Matcher for extracting custom entities
matcher = Matcher(nlp.vocab)
patterns = {
    "WORK_EXPERIENCE": [
        [{"POS": "PROPN", "OP": "+"}, {"LOWER": "at"}, {"POS": "PROPN", "OP": "+"}],
        [{"POS": "NOUN", "OP": "+"}, {"POS": "ADP"}, {"POS": "PROPN", "OP": "+"}],
        [{"POS": "VERB"}, {"POS": "NOUN", "OP": "+"}, {"LOWER": "at"}, {"POS": "PROPN", "OP": "+"}],
    ],
    "CERTIFICATION": [
        [{"LOWER": "certified"}, {"IS_ALPHA": True, "OP": "*"}],
        [{"LOWER": "certificate"}, {"IS_ALPHA": True, "OP": "*"}],
        [{"LOWER": "certification"}, {"IS_ALPHA": True, "OP": "*"}],
    ],
    "CONTACT_INFO": [
        [{"LIKE_EMAIL": True}],
    ]
}

for label, pattern in patterns.items():
    matcher.add(label, pattern)

# Function to extract all information from text
def extract_all_information(text):
    doc = nlp(text)
    extracted_info = {
        "Person Name": [],
        "Skill": [],
        "Work Experience": [],
        "Certification": [],
        "Contact Info": []
    }
    # Extract entities
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            extracted_info["Person Name"].append(ent.text)
        elif ent.label_ == "SKILL":
            extracted_info["Skill"].append(ent.text)
    # Use matcher to find matches
    matches = matcher(doc)
    for match_id, start, end in matches:
        span = doc[start:end]
        label = nlp.vocab.strings[match_id]
        key = label.title().replace("_", " ")
        extracted_info[key].append(span.text)
    for key in extracted_info.keys():
        extracted_info[key] = list(set(extracted_info[key]))
    return extracted_info

# Function to read PDF content using PyPDF2
def read_pdf_content(pdf_file):
    content = ""
    reader = PdfReader(pdf_file)
    for page in reader.pages:
        content += page.extract_text() + " "
    return content

from werkzeug.utils import secure_filename

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        pdf_file = request.files.get('pdf_file')
        if pdf_file and pdf_file.filename.endswith('.pdf'):
            filename = secure_filename(pdf_file.filename)
            session['filename'] = filename.rsplit('.', 1)[0]  # Save the base name of the file
            content = read_pdf_content(pdf_file.stream)
            extracted_info = extract_all_information(content)
            session['extracted_info'] = extracted_info  # Store in session for download
            table_html = generate_table_html(extracted_info)
            return render_template('index.html', table_html=table_html, show_download=True)
    else:
        return render_template('index.html', show_download=False)
    
#------#
def generate_table_html(extracted_info):
    df = pd.DataFrame(list(extracted_info.items()), columns=['Entity Type', 'Extracted Information'])
    return df.to_html(index=False)


@app.route('/download')
def download():
    if 'extracted_info' in session and 'filename' in session:
        extracted_info = session['extracted_info']
        filename = session['filename']  # Retrieve the original file base name
        data = []
        for key, values in extracted_info.items():
            for value in values:
                data.append({"Entity Type": key, "Extracted Information": value})
        df = pd.DataFrame(data)
        csv_data = df.to_csv(index=False)
        response = make_response(csv_data)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}.csv'
        return response
    return "No information available for download", 404

#--#

def generate_dataframe_for_csv(extracted_info):
    # Flatten the extracted information for CSV format
    # Creating a list of dictionaries, each representing a row in the CSV
    rows = []
    for key, values in extracted_info.items():
        for value in values:
            rows.append({"Entity Type": key, "Extracted Information": value})
    # Convert list of dictionaries to a DataFrame
    df = pd.DataFrame(rows)
    return df


if __name__ == '__main__':
    app.run(debug=True)