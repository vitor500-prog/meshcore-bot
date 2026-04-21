from flask import Flask, render_template_string
import threading

TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>MeshCore Dual-Band Dashboard</title>
    <meta http-equiv="refresh" content="30">
    <style>
        body { font-family: sans-serif; background:#0f1117; color:#e0e0e0; padding:20px; }
        h1 { color:#00d4ff; } h2 { color:#00d4ff; margin:20px 0 10px; }
        .subtitle { color:#888; font-size:0.9em; margin-bottom:25px; }
        .grid { display:flex; gap:15px; flex-wrap:wrap; margin-bottom:25px; }
        .card { background:#1a1d27; border-radius:10px; padding:18px; min-width:160px;
                flex:1; border:1px solid #2a2d3a; }
        .card h3 { color:#888; font-size:0.8em; text-transform:uppercase; margin-bottom:8px; }
        .big { font-size:2.2em; font-weight:bold; }
        .c433{color:#ff6b35;} .c868{color:#00d4ff;} .cboth{color:#7cfc00;} .ctotal{color:#fff;}
        table { width:100%; border-collapse:collapse; margin-bottom:25px; font-size:0.88em; }
        th { background:#1a1d27; padding:9px 13px; text-align:left; color:#00d4ff;
             border-bottom:2px solid #2a2d3a; }
        td { padding:7px 13px; border-bottom:1px solid #1e2130; }
        tr:hover td { background:#1e2130; }
        .b { padding:3px 7px; border-radius:20px; font-size:0.78em; font-weight:bold; }
        .b433{background:#ff6b3533;color:#ff6b35;} .b868{background:#00d4ff22;color:#00d4ff;}
        .bboth{background:#7cfc0022;color:#7cfc00;} .bmiss{background:#ff222233;color:#ff4444;}
        .ts { color:#666; font-size:0.8em; }
    </style>
</head>
<body>
    <h1>📡 MeshCore Dual-Band Monitor</h1>
    <p class="subtitle">Auto-refreshes every 30s</p>
    <h2>Overall Stats</h2>
    <div class="grid">
        <div class="card"><h3>Total</h3>
            <div class="big ctotal">{{ s.get('total',0) }}</div></div>
        <div class="card"><h3>433 MHz</h3>
            <div class="big c433">{{ s.get('received_433',0) }}</div>
            <small>{{ s.get('success_rate_433',0) }}% success</small></div>
        <div class="card"><h3>868 MHz</h3>
            <div class="big c868">{{ s.get('received_868',0) }}</div>
            <small>{{ s.get('success_rate_868',0) }}% success</small></div>
        <div class="card"><h3>Both Bands</h3>
            <div class="big cboth">{{ s.get('received_both',0) }}</div>
            <small>{{ s.get('success_rate_both',0) }}% success</small></div>
    </div>
    <h2>Per Channel</h2>
    <table>
        <tr><th>Channel</th><th>Total</th><th>433</th><th>868</th><th>Both</th></tr>
        {% for ch in channels %}
        <tr>
            <td><strong>#{{ ch.channel }}</strong></td>
            <td>{{ ch.total }}</td>
            <td><span class="b b433">{{ ch.r433 }}</span></td>
            <td><span class="b b868">{{ ch.r868 }}</span></td>
            <td><span class="b bboth">{{ ch.both }}</span></td>
        </tr>
        {% else %}
        <tr><td colspan="5" style="color:#666;text-align:center">No data yet</td></tr>
        {% endfor %}
    </table>
    <h2>⚠️ Missed by One Band</h2>
    <table>
        <tr><th>Time</th><th>Channel</th><th>Sender</th><th>Message</th><th>Missed</th></tr>
        {% for m in missed %}
        <tr>
            <td class="ts">{{ m.readable_ts }}</td>
            <td>#{{ m.channel }}</td><td>{{ m.sender }}</td>
            <td>{{ m.text[:50] }}</td>
            <td><span class="b bmiss">{{ m.missed_by }} MHz</span></td>
        </tr>
        {% else %}
        <tr><td colspan="5" style="color:#666;text-align:center">None yet 🎉</td></tr>
        {% endfor %}
    </table>
    <h2>📋 Recent Messages</h2>
    <table>
        <tr><th>Time</th><th>Channel</th><th>Sender</th><th>Message</th><th>First Band</th><th>Both?</th></tr>
        {% for m in recent %}
        <tr>
            <td class="ts">{{ m.readable_ts }}</td>
            <td>#{{ m.channel }}</td><td>{{ m.sender }}</td>
            <td>{{ m.text[:50] }}</td>
            <td>{% if m.first_band=='433' %}<span class="b b433">433</span>
                {% else %}<span class="b b868">868</span>{% endif %}</td>
            <td>{% if m.received_433 and m.received_868 %}
                    <span class="b bboth">✓ Both</span>
                {% else %}<span class="b bmiss">One only</span>{% endif %}</td>
        </tr>
        {% else %}
        <tr><td colspan="6" style="color:#666;text-align:center">No data yet</td></tr>
        {% endfor %}
    </table>
</body>
</html>
"""

def start_dashboard(db, host="0.0.0.0", port=8080):
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(
            TEMPLATE,
            s=db.summary(),
            channels=db.per_channel(),
            missed=db.recent_missed(50),
            recent=db.recent_all(100),
        )

    def run():
        app.run(host=host, port=port, debug=False, use_reloader=False)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    print(f"[Dashboard] http://0.0.0.0:{port}")
