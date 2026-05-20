import os
import json
from pathlib import Path
from graphify.detect import detect  # pyrefly: ignore [missing-import]
from graphify.extract import collect_files, extract  # pyrefly: ignore [missing-import]
from graphify.build import build_from_json  # pyrefly: ignore [missing-import]
from graphify.cluster import cluster, score_all  # pyrefly: ignore [missing-import]
from graphify.analyze import god_nodes, surprising_connections, suggest_questions  # pyrefly: ignore [missing-import]
from graphify.report import generate  # pyrefly: ignore [missing-import]
from graphify.export import to_json, to_html  # pyrefly: ignore [missing-import]

# 1. Detect files
print("Detecting files...")
input_path = Path(".")
detect_res = detect(input_path)
os.makedirs("graphify-out", exist_ok=True)
Path("graphify-out/.graphify_detect.json").write_text(json.dumps(detect_res), encoding="utf-8")

# 2. Extract (AST)
print("Extracting architecture...")
code_files = []
for f in detect_res.get('files', {}).get('code', []):
    code_files.extend(collect_files(Path(f)) if Path(f).is_dir() else [Path(f)])

if code_files:
    # Use cache_root='.' to store extraction cache locally
    extraction = extract(code_files, cache_root=Path('.'))
else:
    extraction = {'nodes': [], 'edges': [], 'input_tokens': 0, 'output_tokens': 0}

# 3. Build & Cluster
print("Building graph and clustering...")
G = build_from_json(extraction)
communities = cluster(G)
cohesion = score_all(G, communities)
gods = god_nodes(G)
surprises = surprising_connections(G, communities)

# LABELS - mapped based on community content
labels = {
    0: "FastAPI Endpoints",
    1: "Database Models",
    7: "Desktop Automation",
    9: "AI & Memory Engine",
    2: "Time Utilities",
    3: "Planner Logic",
    16: "Frontend Navigation",
    8: "Voice & API Comms",
    5: "Session Management",
    10: "Chat Initialization",
    4: "Frontend Interaction"
}
# Fallback for any other communities
for cid in communities:
    if cid not in labels:
        labels[cid] = f"Community {cid}"

questions = suggest_questions(G, communities, labels)

# 4. Generate Outputs
print("Generating reports and visualization...")
report = generate(G, communities, cohesion, labels, gods, surprises, detect_res, 
                  {'input': 0, 'output': 0}, str(input_path.absolute()), 
                  suggested_questions=questions)

Path("graphify-out/GRAPH_REPORT.md").write_text(report, encoding="utf-8")
to_json(G, communities, 'graphify-out/graph.json')
html_path = 'graphify-out/graph.html'
to_html(G, communities, html_path, community_labels=labels)

# Inject Premium CSS and JS
print("Applying premium aesthetics and interactive logic...")
premium_css = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Fira+Code:wght@400;500&display=swap');
  :root {
    --bg: #0b0f19;
    --sidebar-bg: rgba(13, 20, 35, 0.7);
    --border: rgba(255, 255, 255, 0.06);
    --border-glow: rgba(99, 102, 241, 0.2);
    --accent: #6366f1;
    --accent-glow: rgba(99, 102, 241, 0.35);
    --text: #f9fafb;
    --text-muted: #9ca3af;
    --card-bg: rgba(17, 24, 39, 0.4);
    --panel-blur: blur(24px);
    --transition: all 0.25s cubic-bezier(0.25, 0.8, 0.25, 1);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { 
    background: var(--bg); 
    color: var(--text); 
    font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif; 
    display: flex; 
    height: 100vh; 
    overflow: hidden; 
    scrollbar-width: thin;
    scrollbar-color: rgba(255, 255, 255, 0.1) transparent;
  }
  #graph { 
    flex: 1; 
    background: radial-gradient(circle at 50% 50%, #151d30 0%, #080c14 100%); 
    position: relative;
  }
  #graph::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    background-image: radial-gradient(rgba(255, 255, 255, 0.02) 1px, transparent 1px);
    background-size: 32px 32px;
    pointer-events: none;
  }
  #sidebar { 
    width: 350px; 
    background: var(--sidebar-bg); 
    backdrop-filter: var(--panel-blur); 
    -webkit-backdrop-filter: var(--panel-blur);
    border-left: 1px solid var(--border); 
    display: flex; 
    flex-direction: column; 
    overflow: hidden; 
    box-shadow: -10px 0 50px rgba(0,0,0,0.8);
    z-index: 10;
    transition: var(--transition);
  }
  #search-wrap { 
    padding: 24px; 
    border-bottom: 1px solid var(--border); 
    background: rgba(0, 0, 0, 0.15); 
  }
  #search { 
    width: 100%; 
    background: rgba(0, 0, 0, 0.4); 
    border: 1px solid var(--border); 
    color: var(--text); 
    padding: 14px 18px; 
    border-radius: 12px; 
    font-size: 14px; 
    font-weight: 500;
    font-family: inherit;
    outline: none; 
    transition: var(--transition);
    box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.5);
  }
  #search:focus { 
    border-color: var(--accent); 
    box-shadow: 0 0 20px var(--border-glow), inset 0 2px 8px rgba(0, 0, 0, 0.5);
    background: rgba(0, 0, 0, 0.6);
  }
  #search-results { 
    max-height: 220px; 
    overflow-y: auto; 
    background: rgba(0, 0, 0, 0.2);
    border-bottom: 1px solid var(--border);
  }
  .search-item { 
    padding: 12px 24px; 
    cursor: pointer; 
    font-size: 13px; 
    color: var(--text-muted);
    transition: var(--transition);
    border-left: 3px solid transparent;
  }
  .search-item:hover { 
    background: rgba(99, 102, 241, 0.08); 
    color: var(--text);
    border-left-color: var(--accent);
    padding-left: 28px;
  }
  #info-panel { 
    padding: 28px 24px; 
    border-bottom: 1px solid var(--border); 
    flex-shrink: 0; 
  }
  #info-panel h3 { 
    font-size: 11px; 
    color: var(--accent); 
    margin-bottom: 20px; 
    text-transform: uppercase; 
    letter-spacing: 0.2em; 
    font-weight: 800; 
    display: flex;
    align-items: center;
    gap: 8px;
    text-shadow: 0 0 12px var(--accent-glow);
  }
  #info-panel h3::after { 
    content: ''; 
    flex: 1; 
    height: 1px; 
    background: linear-gradient(90deg, var(--border) 0%, transparent 100%); 
  }
  #info-content { 
    font-size: 14px; 
    color: #f3f4f6; 
    line-height: 1.6; 
  }
  #info-content .field { 
    margin-bottom: 16px; 
  }
  #info-content .field b { 
    color: var(--text-muted); 
    font-size: 10px; 
    display: block;
    margin-bottom: 6px; 
    text-transform: uppercase; 
    letter-spacing: 0.1em; 
    font-weight: 700;
  }
  #info-content .val {
    background: rgba(0, 0, 0, 0.25);
    padding: 10px 14px;
    border-radius: 8px;
    border: 1px solid var(--border);
    word-break: break-all;
    font-family: 'Fira Code', monospace;
    font-size: 12px;
    color: #e5e7eb;
    box-shadow: inset 0 2px 4px rgba(0,0,0,0.4);
  }
  #info-content .empty { 
    color: var(--text-muted); 
    font-style: italic; 
    text-align: center; 
    padding: 40px 0; 
    opacity: 0.5; 
    font-size: 13px; 
  }
  .neighbor-link { 
    display: flex;
    align-items: center;
    padding: 12px 16px; 
    margin: 8px 0; 
    border-radius: 10px; 
    cursor: pointer; 
    font-size: 13px; 
    background: rgba(255, 255, 255, 0.015);
    border: 1px solid var(--border);
    border-left: 3px solid rgba(255, 255, 255, 0.25);
    transition: var(--transition);
    color: var(--text);
    box-shadow: 0 2px 4px rgba(0,0,0,0.15);
  }
  .neighbor-link:hover { 
    background: rgba(99, 102, 241, 0.08); 
    border-color: var(--accent);
    transform: translateX(6px);
    box-shadow: 0 4px 16px rgba(0,0,0,0.3);
  }
  #legend-wrap { 
    flex: 1; 
    overflow-y: auto; 
    padding: 24px; 
  }
  #legend-wrap h3 { 
    font-size: 11px; 
    color: var(--accent); 
    margin-bottom: 24px; 
    text-transform: uppercase; 
    letter-spacing: 0.2em; 
    font-weight: 800; 
    display: flex;
    align-items: center;
    gap: 8px;
    text-shadow: 0 0 12px var(--accent-glow);
  }
  #legend-wrap h3::after { 
    content: ''; 
    flex: 1; 
    height: 1px; 
    background: linear-gradient(90deg, var(--border) 0%, transparent 100%); 
  }
  .legend-item { 
    display: flex; 
    align-items: center; 
    gap: 16px; 
    padding: 12px 16px; 
    cursor: pointer; 
    border-radius: 12px; 
    font-size: 13px; 
    transition: var(--transition);
    margin-bottom: 6px;
    border: 1px solid transparent;
  }
  .legend-item:hover { 
    background: rgba(255, 255, 255, 0.03); 
    border-color: var(--border);
    transform: translateX(4px);
  }
  .legend-item.dimmed { 
    opacity: 0.15; 
    filter: grayscale(1); 
    transform: scale(0.97); 
  }
  .legend-dot { 
    width: 12px; 
    height: 12px; 
    border-radius: 4px; 
    box-shadow: 0 0 10px currentColor; 
    flex-shrink: 0; 
  }
  .legend-label { 
    flex: 1; 
    white-space: nowrap; 
    overflow: hidden; 
    text-overflow: ellipsis; 
    font-weight: 600; 
    color: #e5e7eb; 
  }
  .legend-count { 
    font-family: 'Fira Code', monospace;
    background: rgba(0,0,0,0.3);
    padding: 3px 10px;
    border-radius: 6px;
    color: var(--text-muted); 
    font-size: 10px; 
    font-weight: 600; 
  }
  #stats { 
    padding: 20px 24px; 
    background: rgba(0, 0, 0, 0.35); 
    border-top: 1px solid var(--border); 
    font-size: 10px; 
    color: var(--text-muted); 
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-weight: 600;
  }
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.08); border-radius: 10px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--accent); }
</style>
"""

premium_js = """
<script>
// Cyber-Minimalist Interface Logic
(function() {
  const TYPE_SHAPES = {
    'code': 'dot',
    'rationale': 'star',
    'config': 'square',
    'data': 'database',
    'logic': 'diamond',
    'unknown': 'dot'
  };

  // Enhance node visual properties before initialization
  const enhancedNodes = RAW_NODES.map(n => {
    let shape = TYPE_SHAPES[n.file_type] || 'dot';
    // God nodes get special treatment
    if (n.degree > 15) shape = 'hexagon'; 
    
    return {
      ...n,
      shape: shape,
      borderWidth: 2,
      shadow: { enabled: true, color: 'rgba(0,0,0,0.4)', size: 8, x: 4, y: 4 },
      font: { 
        size: n.degree > 10 ? 14 : 0, 
        color: '#f3f4f6', 
        face: 'Inter',
        strokeWidth: 2,
        strokeColor: '#030712'
      },
      margin: 10
    };
  });

  // Override the nodesDS initialization by monkey-patching or manual update
  // Since we are injecting after the script, we can update the existing nodesDS
  if (window.nodesDS) {
    nodesDS.update(enhancedNodes);
  }

  // Update Network Options for premium feel
  if (window.network) {
    network.setOptions({
      nodes: {
        scaling: { min: 10, max: 30 },
        borderWidthSelected: 4,
        color: {
          highlight: { background: '#ffffff', border: '#6366f1' },
          hover: { background: '#6366f1', border: '#ffffff' }
        }
      },
      edges: {
        color: { color: 'rgba(255,255,255,0.12)', highlight: '#6366f1', hover: '#818cf8', opacity: 0.6 },
        smooth: { type: 'cubicBezier', forceDirection: 'none', roundness: 0.5 },
        selectionWidth: 4,
        hoverWidth: 2
      },
      interaction: {
        hover: true,
        tooltipDelay: 100,
        zoomView: true
      }
    });
  }

  // Improved showInfo with premium layout
  window.showInfo = function(nodeId) {
    const n = nodesDS.get(nodeId);
    if (!n) return;
    const neighborIds = network.getConnectedNodes(nodeId);
    const neighborItems = neighborIds.map(nid => {
      const nb = nodesDS.get(nid);
      const color = nb ? nb.color.background : '#555';
      return `<div class="neighbor-link" style="border-left-color:${color}" onclick="focusNode('${nid}')">${nb ? nb.label : nid}</div>`;
    }).join('');
    
    document.getElementById('info-content').innerHTML = `
      <div class="field"><b>Name</b><div class="val">${n.label}</div></div>
      <div class="field"><b>Type</b><div class="val">${n._file_type || 'system'}</div></div>
      <div class="field"><b>Community</b><div class="val">${n._community_name}</div></div>
      <div class="field"><b>Relations</b><div class="val">${n._degree} connections</div></div>
      ${neighborIds.length ? `<div class="field" style="margin-top:20px"><b>Connected To</b><div>${neighborItems}</div></div>` : ''}
    `;
  };
})();
</script>
"""

html_content = Path(html_path).read_text(encoding="utf-8")
import re

# 1. Replace the existing style block
html_content = re.sub(r'<style>.*?</style>', premium_css, html_content, flags=re.DOTALL)

# 2. Inject the premium JS before the closing body tag
if '</body>' in html_content:
    html_content = html_content.replace('</body>', premium_js + '</body>')

# 3. Minor HTML fixes for the premium layout (adding wrappers if needed, though existing structure is okay)
# We'll just update the stats to look more 'cyber'
html_content = html_content.replace('Node Info', 'Architecture Intel')
html_content = html_content.replace('>Communities<', '>System Sectors<')

Path(html_path).write_text(html_content, encoding="utf-8")

print("\nSuccess! Knowledge graph interface modernized in graphify-out/")
print("  - Aesthetic: Cyber-Minimalist")
print("  - Engine: Premium Vis-Network Overrides")
