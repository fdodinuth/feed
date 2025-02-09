# app.py
from flask import Flask, render_template, request, jsonify, send_file
from datetime import datetime
import sqlite3
import qrcode
import pandas as pd
import os
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'  # Required for SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# Database initialization
def init_db():
    conn = sqlite3.connect('feedback.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS feedback
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  rating FLOAT NOT NULL,
                  comment TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

# Generate QR Code
def generate_qr():
    try:
        # Get the server's URL (replace with your actual URL in production)
        url = "http://127.0.0.1:5000/"
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url) 
        qr.make(fit=True)

        # Create QR code image
        qr_image = qr.make_image(fill_color="black", back_color="white")
        
        # Ensure static directory exists
        if not os.path.exists('static'):
            os.makedirs('static')
            
        # Save QR code
        qr_image.save('static/feedback_qr.png')
    except Exception as e:
        print(f"Error generating QR code: {e}")

# Initialize database and generate QR code
init_db()
generate_qr()

@app.route('/')
def feedback_form():
    return render_template('feedback.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    try:
        rating = request.form.get('rating')
        comment = request.form.get('comment')
        
        if not rating:
            return jsonify({'error': 'Rating is required'}), 400
        
        conn = sqlite3.connect('feedback.db')
        c = conn.cursor()
        c.execute("""INSERT INTO feedback (rating, comment, created_at) 
                    VALUES (?, ?, datetime('now', 'localtime'))""",
                 (rating, comment))
        conn.commit()
        
        # Get the inserted feedback with its ID
        c.execute("""SELECT id, rating, comment, datetime(created_at) as created_at 
                    FROM feedback WHERE id = last_insert_rowid()""")
        row = c.fetchone()
        conn.close()
        
        # Prepare feedback data for socket emission
        feedback_data = {
            'id': row[0],
            'rating': float(row[1]),
            'comment': row[2],
            'created_at': row[3]
        }
        
        # Emit new feedback to all connected clients
        socketio.emit('new_feedback', feedback_data)
        
        return jsonify({'success': True, 'feedback': feedback_data})
    except Exception as e:
        print(f"Error submitting feedback: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/get_feedback')
def get_feedback():
    try:
        conn = sqlite3.connect('feedback.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        c.execute("""SELECT id, rating, comment, 
                    datetime(created_at) as created_at 
                    FROM feedback 
                    ORDER BY created_at DESC""")
        
        rows = c.fetchall()
        feedback = [{
            'id': row['id'],
            'rating': float(row['rating']),
            'comment': row['comment'],
            'created_at': row['created_at']
        } for row in rows]
        
        conn.close()
        return jsonify(feedback)
    except Exception as e:
        print(f"Error getting feedback: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/get_stats')
def get_stats():
    try:
        conn = sqlite3.connect('feedback.db')
        c = conn.cursor()
        
        c.execute("""
            SELECT 
                COUNT(*) as total_feedback,
                AVG(rating) as avg_rating,
                COUNT(CASE WHEN rating = 5 THEN 1 END) as five_star,
                COUNT(CASE WHEN rating = 4 THEN 1 END) as four_star,
                COUNT(CASE WHEN rating = 3 THEN 1 END) as three_star,
                COUNT(CASE WHEN rating = 2 THEN 1 END) as two_star,
                COUNT(CASE WHEN rating = 1 THEN 1 END) as one_star
            FROM feedback
        """)
        
        stats = c.fetchone()
        conn.close()
        
        return jsonify({
            'total_feedback': stats[0],
            'average_rating': round(stats[1], 2) if stats[1] else 0,
            'rating_distribution': {
                '5': stats[2],
                '4': stats[3],
                '3': stats[4],
                '2': stats[5],
                '1': stats[6]
            }
        })
    except Exception as e:
        print(f"Error getting stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/export_excel')
def export_excel():
    try:
        conn = sqlite3.connect('feedback.db')
        query = """
            SELECT 
                id,
                rating,
                comment,
                datetime(created_at) as submitted_date
            FROM feedback 
            ORDER BY created_at DESC
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        # Create Excel file
        excel_file = 'feedback_export.xlsx'
        writer = pd.ExcelWriter(excel_file, engine='openpyxl')
        df.to_excel(writer, sheet_name='Feedback', index=False)
        
        # Auto-adjust columns' width
        worksheet = writer.sheets['Feedback']
        for idx, col in enumerate(df.columns):
            max_length = max(df[col].astype(str).apply(len).max(), len(col)) + 2
            worksheet.column_dimensions[chr(65 + idx)].width = max_length
            
        writer.close()
        
        return send_file(
            excel_file,
            as_attachment=True,
            download_name=f'feedback_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
    except Exception as e:
        print(f"Error exporting to Excel: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/qr')
def get_qr():
    try:
        return send_file('static/feedback_qr.png', mimetype='image/png')
    except Exception as e:
        print(f"Error serving QR code: {e}")
        return jsonify({'error': str(e)}), 500

# SocketIO event handlers
@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

if __name__ == '__main__':
    # Create static folder if it doesn't exist
    if not os.path.exists('static'):
        os.makedirs('static')
    
    # Run the app with SocketIO
    socketio.run(app, debug=True)
