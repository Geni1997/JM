from flask import Flask, request, send_file, render_template_string, jsonify
import tempfile
import io
import os
import pypandoc
import fitz  # PyMuPDF för PDF-hantering
from PIL import Image
import pytesseract
import zipfile
import uuid
from datetime import datetime, timedelta

# Ange den exakta sökvägen till pandoc
pypandoc.pandoc_path = r"C:\Program Files\Pandoc\pandoc.exe"

app = Flask(__name__)

@app.route('/')
def index():
    with open("static/index.html") as f:
        return render_template_string(f.read())

# ---- Dokumentkonvertering utan permanent lagring ----
@app.route('/convert_document', methods=['POST'])
def convert_document():
    if 'file' not in request.files:
        return "Ingen fil uppladdad", 400

    file = request.files['file']
    if file.filename == '':
        return "Ingen fil vald", 400

    output_format = request.form.get("format")
    if output_format not in ["pdf", "docx", "txt", "html", "md", "odt", "epub"]:
        return "Ogiltigt format", 400

    input_ext = os.path.splitext(file.filename)[1].lower()

    # Hantera PDF-indata separat
    if input_ext == ".pdf":
        pdf_text = ""
        with fitz.open(stream=file.read(), filetype="pdf") as pdf_doc:
            for page_num in range(pdf_doc.page_count):
                page = pdf_doc[page_num]
                pdf_text += page.get_text()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".md", mode='w', encoding='utf-8') as temp_pdf_markdown_file:
            temp_pdf_markdown_file.write(pdf_text)
            temp_pdf_markdown_file_path = temp_pdf_markdown_file.name

        temp_output_file = tempfile.NamedTemporaryFile(delete=False, suffix=f".{output_format}")
        temp_output_file.close()
        
        # Konvertera med pandoc och specificera PDF-motorn xelatex
        pypandoc.convert_file(
            temp_pdf_markdown_file_path,
            output_format,
            outputfile=temp_output_file.name,
            extra_args=["--pdf-engine=xelatex"]
        )
        os.remove(temp_pdf_markdown_file_path)

        response = send_file(temp_output_file.name, as_attachment=True, download_name=f"converted_document.{output_format}")
        @response.call_on_close
        def cleanup():
            os.remove(temp_output_file.name)

        return response

    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=input_ext) as temp_input_file:
            file.save(temp_input_file.name)
            temp_input_file_path = temp_input_file.name

        temp_output_file = tempfile.NamedTemporaryFile(delete=False, suffix=f".{output_format}")
        temp_output_file.close()

        # Utför konverteringen efter att ha stängt filen
        pypandoc.convert_file(temp_input_file_path, output_format, outputfile=temp_output_file.name)
        os.remove(temp_input_file_path)

        response = send_file(temp_output_file.name, as_attachment=True, download_name=f"converted_document.{output_format}")
        @response.call_on_close
        def cleanup():
            os.remove(temp_output_file.name)

        return response

# ---- Bildkonvertering utan permanent lagring ----
@app.route('/convert_image', methods=['POST'])
def convert_image():
    if 'file' not in request.files:
        return "Ingen fil uppladdad", 400

    file = request.files['file']
    if file.filename == '':
        return "Ingen fil vald", 400

    output_format = request.form.get("format")
    if output_format not in ["JPEG", "PNG", "GIF", "BMP", "TIFF"]:
        return "Ogiltigt format", 400

    img = Image.open(file.stream)
    img = img.convert("RGB") if output_format in ["JPEG", "BMP"] else img

    img_io = io.BytesIO()
    img.save(img_io, format=output_format)
    img_io.seek(0)

    return send_file(img_io, as_attachment=True, download_name=f"converted_image.{output_format.lower()}", mimetype=f"image/{output_format.lower()}")



# ---- Batchkonvertering och zip-nedladdning ----
@app.route('/batch_convert', methods=['POST'])
def batch_convert():
    files = request.files.getlist("files")
    zip_io = io.BytesIO()

    with zipfile.ZipFile(zip_io, 'w') as zipf:
        for file in files:
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_input_file:
                file.save(temp_input_file.name)
                temp_input_file_path = temp_input_file.name

            temp_output_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
            temp_output_file.close()

            # Lägg till konverterad fil i zip
            zipf.write(temp_output_file.name, file.filename)
            os.remove(temp_output_file.name)
            os.remove(temp_input_file_path)

    zip_io.seek(0)
    return send_file(zip_io, as_attachment=True, download_name="batch_converted.zip", mimetype="application/zip")

# ---- Dela-funktion med tidsbegränsning ----
shared_files = {}

@app.route('/share_file', methods=['POST'])
def share_file():
    file = request.files.get('file')
    expiration_minutes = int(request.form.get('expiration', 10))
    if file:
        temp_path = io.BytesIO()
        file.save(temp_path)
        temp_path.seek(0)

        expiration_time = datetime.now() + timedelta(minutes=expiration_minutes)
        shared_id = uuid.uuid4().hex
        shared_files[shared_id] = {"file": temp_path, "expires": expiration_time, "filename": file.filename}

        share_link = f"http://127.0.0.1:5000/download/{shared_id}"
        return jsonify({"share_link": share_link})
    return jsonify({"error": "Ingen fil uppladdad"}), 400

@app.route('/download/<shared_id>')
def download_shared_file(shared_id):
    shared_info = shared_files.get(shared_id)
    if shared_info and datetime.now() < shared_info["expires"]:
        return send_file(
            shared_info["file"], 
            as_attachment=True, 
            download_name=shared_info["filename"],  # Ange filnamn för nedladdning
            mimetype="application/octet-stream"  # Generisk binär mimetyp
        )
    return jsonify({"error": "Länken har gått ut eller är ogiltig"}), 404

if __name__ == "__main__":
    app.run(debug=True)
