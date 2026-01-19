import os
import io
import base64
from flask import Flask, render_template, request, jsonify
import anthropic
import pypdfium2 as pdfium

app = Flask(__name__)

# Maximum file size: 50MB
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024


@app.route('/')
def index():
    """Serve the main page."""
    return render_template('index.html')


@app.route('/analyze', methods=['POST'])
def analyze_pdf():
    """Analyze an uploaded PDF page by page using Claude."""
    if 'pdf' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['pdf']

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Please upload a PDF file'}), 400

    try:
        # Read PDF data
        pdf_data = file.read()

        # Open PDF with pypdfium2
        pdf = pdfium.PdfDocument(pdf_data)
        total_pages = len(pdf)

        # Create Anthropic client
        client = anthropic.Anthropic()

        results = []

        for page_num in range(total_pages):
            page = pdf[page_num]

            # Render page to PIL Image for thumbnail (scale=1 is 72 DPI)
            bitmap_thumb = page.render(scale=1.0)
            pil_thumb = bitmap_thumb.to_pil()

            # Convert thumbnail to base64 PNG
            thumb_buffer = io.BytesIO()
            pil_thumb.save(thumb_buffer, format='PNG')
            thumb_buffer.seek(0)
            thumbnail_base64 = base64.standard_b64encode(thumb_buffer.read()).decode('utf-8')

            # Render higher resolution for Claude analysis (scale=2 is 144 DPI)
            bitmap_hires = page.render(scale=2.0)
            pil_hires = bitmap_hires.to_pil()

            # Convert high-res to base64 PNG
            hires_buffer = io.BytesIO()
            pil_hires.save(hires_buffer, format='PNG')
            hires_buffer.seek(0)
            analysis_base64 = base64.standard_b64encode(hires_buffer.read()).decode('utf-8')

            # Send page image to Claude for analysis
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": analysis_base64
                                }
                            },
                            {
                                "type": "text",
                                "text": f"""Describe the layout of this PDF page (page {page_num + 1} of {total_pages}). Include:
- Text layout (columns, headers, paragraphs, lists)
- Visual elements (images, charts, tables, diagrams)
- Formatting details (fonts, colors, spacing if notable)
- Overall organization of the page

Be concise but thorough. Focus on layout structure rather than content."""
                            }
                        ]
                    }
                ]
            )

            description = message.content[0].text

            results.append({
                'page': page_num + 1,
                'thumbnail': thumbnail_base64,
                'description': description
            })

        pdf.close()
        return jsonify({'pages': results})

    except anthropic.APIError as e:
        return jsonify({'error': f'API error: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': f'Error processing PDF: {str(e)}'}), 500


if __name__ == '__main__':
    if not os.environ.get('ANTHROPIC_API_KEY'):
        print("Warning: ANTHROPIC_API_KEY environment variable not set!")
        print("Set it with: set ANTHROPIC_API_KEY=your-api-key")

    app.run(debug=True, port=5000)
