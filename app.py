from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import pandas as pd
import io, os, json, base64
from email.mime.text import MIMEText

app = Flask(__name__)
CORS(app)

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/spreadsheets',
]
CREDS_FILE  = 'credentials.json'
TOKEN_FILE  = 'google_token.json'
READY_TO_INGEST_ID = '1_7I5T3s04L4WLJh11CI9yiHwgzpu81Nn'

def get_google_creds():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())
    return creds

print("=" * 50)
print("🎵  SONGXS")
print("=" * 50)
creds = get_google_creds()
print("✅ Google autenticado")
print("=" * 50)

# Columns (no UPC)
HEADERS = [
    'ARTIST', 'ALBUM NAME', 'TRACK NAME', 'ISRC',
    'LYRICS FOLDER',
    '100% CONTROLLED MASTER (?)',
    'IF NOT 100% SPECIFY % CONTROLLED & EMAIL CONTACT(S) [MASTER]',
    '100% CONTROLLED PUBLISHING (?)',
    'IF NOT 100% SPECIFY % CONTROLLED & EMAIL CONTACT(S) [PUBLISHING]',
    'TIER', 'BID or PRICE',
    'PAID MEDIA OPT-IN (ARTISTPROMO TIER ONLY)',
    'ARCHIVAL RESTRICTION', 'YOUTUBE RESTRICTION',
    'DISTRIBUTOR NAME', "DISTRIBUTOR'S EMAIL",
    'RESTRICTED CLUBS', 'INSTAGRAM HANDLE', 'TIKTOK HANDLE', 'YOUTUBE HANDLE',
]

INSTRUCTIONS = [
    ['CONTROLLED MASTER (?)', 'Do you own or control 100% of the MASTER rights of this song?\nTick box if YES'],
    ['CONTROLLED PUBLISHING (?)', 'Do you own or control 100% of the PUBLISHING rights of this song?\nTick box if YES'],
    ['IF NOT 100% CONTROLLED SPECIFY EMAIL CONTACTS', 'Include email addresses for any other rightsholders who own or control the recording and/or composition.'],
    ['TIER', 'Bid2Clear\n• Bidding process, you provide a suggested bid\nPreClear\n• You set the price\nArtistPromo\n• No set price, payments depend on the usage-based prorata share of the subscription pool (70% of total subscriptions)'],
    ['BID or PRICE', 'Specify suggested bid for the Bid2Clear tier or determine a set price for the PreClear tier.\nIf ArtistPromo, leave this blank.'],
    ['PAID MEDIA OPT-IN (ARTISTPROMO TIER ONLY)', 'Would you like to make the track available for social media paid campaigns (brand sponsorships, season tickets sales, jersey sales...). If so, you will receive a direct, flat $210 payment per use for those types of non-editorial campaigns.'],
    ['ARCHIVAL RESTRICTION', 'Sports organizations prefer not to remove content sitting passively on their social media walls. However, if you\'d like to request removal of the content after some time, add a duration restriction (cannot be less that one year).\nNOTE: this might affect your chances of licensing your music.'],
    ['YOUTUBE RESTRICTION', 'Sports organizations prefer not to remove content from their YouTube channels. However, if you\'d like to request their video be set to "unlisted" after some time, add a duration restriction (cannot be less that one year).\nNOTE: this might affect your chances of licensing your music.'],
    ['DISTRIBUTOR NAME', 'Who distributes this song digitally (e.g. Tunecore, DistroKid, The Orchard, Symponic etc...)?'],
    ["DISTRIBUTOR'S EMAIL", 'Provide an email contact for your digital music distribution partner.'],
    ['RESTRICTED CLUBS', 'Are there any teams you rather NOT use your music in their content?'],
]

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/upload-csv', methods=['POST'])
def upload_csv():
    try:
        file = request.files.get('file')
        if not file:
            return jsonify({'error': 'No se recibió archivo'}), 400
        content = file.read().decode('utf-8')
        df = pd.read_csv(io.StringIO(content))
        tracks = []
        for _, row in df.iterrows():
            def get(es, en):
                if es in df.columns: return str(row.get(es, '') or '')
                return str(row.get(en, '') or '')
            tracks.append({
                'ARTIST':     get('Nombre(s) del artista', 'Artist Name(s)'),
                'ALBUM NAME': get('Nombre del álbum', 'Album Name'),
                'TRACK NAME': get('Nombre de la canción', 'Track Name'),
                'ISRC':       get('ISRC', 'ISRC'),
            })
        return jsonify({'success': True, 'tracks': tracks, 'total': len(tracks)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/create-folders', methods=['POST'])
def create_folders():
    try:
        data = request.get_json()
        artist_name = data.get('artistName', '').strip()
        if not artist_name:
            return jsonify({'error': 'Nombre de artista requerido'}), 400

        drive = build('drive', 'v3', credentials=get_google_creds())

        def create_folder(name, parent_id):
            meta = {
                'name': name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id],
            }
            f = drive.files().create(body=meta, fields='id,webViewLink').execute()
            return f['id'], f['webViewLink']

        artist_id, artist_link = create_folder(artist_name, READY_TO_INGEST_ID)
        mp3_id, _              = create_folder('MP3 FILES', artist_id)
        lyrics_id, _           = create_folder('LYRICS', artist_id)

        return jsonify({
            'success': True,
            'artistFolderId':   artist_id,
            'artistFolderLink': artist_link,
            'mp3FolderId':      mp3_id,
            'lyricsFolderId':   lyrics_id,
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/create-sheet', methods=['POST'])
def create_sheet():
    try:
        data        = request.get_json()
        artist_name = data.get('artistName', '').strip()
        folder_id   = data.get('folderId', '').strip()
        tracks      = data.get('tracks', [])

        sheets = build('sheets', 'v4', credentials=get_google_creds())
        drive  = build('drive',  'v3', credentials=get_google_creds())

        # Create spreadsheet with 2 sheets
        spreadsheet = sheets.spreadsheets().create(body={
            'properties': {'title': f'CATALOG INGESTION - {artist_name}'},
            'sheets': [
                {'properties': {'title': 'INGESTION TEMPLATE', 'index': 0}},
                {'properties': {'title': 'INSTRUCTIONS', 'index': 1}},
            ],
        }).execute()

        sheet_id   = spreadsheet['spreadsheetId']
        sheet_link = f'https://docs.google.com/spreadsheets/d/{sheet_id}'

        # Get real sheet IDs
        template_sheet_id    = spreadsheet['sheets'][0]['properties']['sheetId']
        instructions_sheet_id = spreadsheet['sheets'][1]['properties']['sheetId']

        # ── INGESTION TEMPLATE data ───────────────────────────────────────────
        rows = [HEADERS]
        for t in tracks:
            rows.append([
                t.get('ARTIST',''), t.get('ALBUM NAME',''),
                t.get('TRACK NAME',''), t.get('ISRC',''),
                *[''] * (len(HEADERS) - 4)
            ])

        sheets.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range='INGESTION TEMPLATE!A1',
            valueInputOption='RAW',
            body={'values': rows},
        ).execute()

        # ── INSTRUCTIONS data ─────────────────────────────────────────────────
        instr_rows = [['FIELD', 'DESCRIPTION']] + INSTRUCTIONS
        sheets.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range='INSTRUCTIONS!A1',
            valueInputOption='RAW',
            body={'values': instr_rows},
        ).execute()

        # ── Formatting ────────────────────────────────────────────────────────
        requests = [
            # Bold headers on INGESTION TEMPLATE
            {'repeatCell': {
                'range': {'sheetId': template_sheet_id, 'startRowIndex': 0, 'endRowIndex': 1},
                'cell': {'userEnteredFormat': {'textFormat': {'bold': True}, 'backgroundColor': {'red': 0.2, 'green': 0.2, 'blue': 0.2}}},
                'fields': 'userEnteredFormat.textFormat.bold,userEnteredFormat.backgroundColor',
            }},
            # Bold headers on INSTRUCTIONS
            {'repeatCell': {
                'range': {'sheetId': instructions_sheet_id, 'startRowIndex': 0, 'endRowIndex': 1},
                'cell': {'userEnteredFormat': {'textFormat': {'bold': True}}},
                'fields': 'userEnteredFormat.textFormat.bold',
            }},
            # Bold column A on INSTRUCTIONS
            {'repeatCell': {
                'range': {'sheetId': instructions_sheet_id, 'startRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 1},
                'cell': {'userEnteredFormat': {'textFormat': {'bold': True}}},
                'fields': 'userEnteredFormat.textFormat.bold',
            }},
            # Wrap text on INSTRUCTIONS col B
            {'repeatCell': {
                'range': {'sheetId': instructions_sheet_id, 'startColumnIndex': 1, 'endColumnIndex': 2},
                'cell': {'userEnteredFormat': {'wrapStrategy': 'WRAP'}},
                'fields': 'userEnteredFormat.wrapStrategy',
            }},
            # Freeze header row on INGESTION TEMPLATE
            {'updateSheetProperties': {
                'properties': {'sheetId': template_sheet_id, 'gridProperties': {'frozenRowCount': 1}},
                'fields': 'gridProperties.frozenRowCount',
            }},
            # Auto resize col A and B on INSTRUCTIONS
            {'autoResizeDimensions': {
                'dimensions': {'sheetId': instructions_sheet_id, 'dimension': 'COLUMNS', 'startIndex': 0, 'endIndex': 2}
            }},
        ]

        sheets.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={'requests': requests},
        ).execute()

        # Move to artist folder
        drive.files().update(
            fileId=sheet_id,
            addParents=folder_id,
            removeParents='root',
            fields='id,parents',
        ).execute()

        return jsonify({'success': True, 'sheetId': sheet_id, 'sheetLink': sheet_link})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/share-files', methods=['POST'])
def share_files():
    try:
        data      = request.get_json()
        folder_id = data.get('folderId')
        sheet_id  = data.get('sheetId')
        email     = data.get('email')
        drive = build('drive', 'v3', credentials=get_google_creds())
        permission = {'type': 'user', 'role': 'writer', 'emailAddress': email}
        drive.permissions().create(fileId=folder_id, body=permission, sendNotificationEmail=False).execute()
        drive.permissions().create(fileId=sheet_id,  body=permission, sendNotificationEmail=False).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/send-email', methods=['POST'])
def send_email():
    try:
        data        = request.get_json()
        to          = data.get('to')
        artist_name = data.get('artistName')
        folder_link = data.get('folderLink')
        sheet_link  = data.get('sheetLink')

        body = f"""Hey everyone,

Please find the Drive folder attached. This contains the CATALOG INGESTION SHEET, and 2 sub-folders (one for uploading your mp3 and one for uploading your lyrics).

Folder: {folder_link}
Catalog Ingestion Sheet: {sheet_link}

Important: Please name the mp3 after the ISRC.

Let me know if you have any questions.

Best,
Juan"""

        msg = MIMEText(body)
        msg['to']      = to
        msg['subject'] = f'Catalog Ingestion - {artist_name}'

        gmail = build('gmail', 'v1', credentials=get_google_creds())
        raw   = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        gmail.users().messages().send(userId='me', body={'raw': raw}).execute()

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download/excel', methods=['POST'])
def download():
    try:
        tracks = request.get_json().get('tracks', [])
        if not tracks:
            return jsonify({'error': 'No data'}), 400
        cols = HEADERS
        df = pd.DataFrame(tracks)
        for c in cols:
            if c not in df.columns: df[c] = ''
        df = df[[c for c in cols if c in df.columns]]
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Tracks')
            ws = writer.sheets['Tracks']
            for col_cells in ws.columns:
                w = max((len(str(c.value)) if c.value else 0) for c in col_cells)
                ws.column_dimensions[col_cells[0].column_letter].width = min(w+4, 50)
        output.seek(0)
        return send_file(output,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True, download_name='songxs_export.xlsx')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
