from weasyprint import HTML
from flask import render_template
import os

def generate_invoice_pdf(invoice_data):
    """Renders the HTML template and converts it to a physical PDF file."""
    # Render the HTML as a string
    rendered_html = render_template('billing/invoice_template.html', invoice=invoice_data)
    
    pdf_path = f"/tmp/invoice_{invoice_data.invoice_number}.pdf"
    
    # Convert HTML string directly to PDF using WeasyPrint
    HTML(string=rendered_html).write_pdf(pdf_path)
    
    return pdf_path