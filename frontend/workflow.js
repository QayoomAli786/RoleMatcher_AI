/* ═══════════════════════════════════════════════════════════════════════════
   Workflow Canvas — nodes drift randomly, particles flow between them
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
    const canvas = document.getElementById('workflow-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let W, H, dpr;
    let nodes = [], edges = [], particles = [];
    let mouse = { x: -9999, y: -9999 };
    let raf;

    function isLightTheme() {
        return document.body.classList.contains('light-theme');
    }

    function getThemeColors() {
        if (isLightTheme()) {
            return {
                grid: 'rgba(0,0,0,0.04)',
                edgeGrad: ['rgba(62,207,142,0.06)', 'rgba(26,173,109,0.04)', 'rgba(62,207,142,0.06)'],
                edgeDash: 'rgba(0,0,0,0.04)',
                nodeFill: 'rgba(255,255,255,0.9)',
                nodeStroke: 'rgba(62,207,142,0.2)',
                nodeIcon: 'rgba(62,207,142,0.6)',
                nodeLabel: 'rgba(0,0,0,0.35)',
                glowColor: 'rgba(62,207,142,'
            };
        }
        return {
            grid: 'rgba(255,255,255,0.008)',
            edgeGrad: ['rgba(62,207,142,0.02)', 'rgba(26,173,109,0.015)', 'rgba(62,207,142,0.02)'],
            edgeDash: 'rgba(255,255,255,0.008)',
            nodeFill: 'rgba(23,23,23,0.8)',
            nodeStroke: 'rgba(62,207,142,',
            nodeIcon: 'rgba(62,207,142,',
            nodeLabel: 'rgba(163,163,163,',
            glowColor: 'rgba(62,207,142,'
        };
    }

    const NODE_LABELS = [
        'Resume', 'Parse', 'Skills', 'Jobs', 'ATS Score',
        'Career Plan', 'Skill Gaps', 'Interview', 'Cover Letter', 'AI Coach'
    ];
    const ICON_GLYPHS = [
        '\uf15c', '\uf085', '\uf5ee', '\uf0b1', '\uf3ed',
        '\uf201', '\uf6aa', '\uf086', '\uf2b6', '\uf544'
    ];

    function noise(seed) {
        return (Math.sin(seed * 127.1 + seed * 311.7) * 43758.5453) % 1;
    }

    function resize() {
        dpr = window.devicePixelRatio || 1;
        W = window.innerWidth;
        H = window.innerHeight;
        canvas.width = W * dpr;
        canvas.height = H * dpr;
        canvas.style.width = W + 'px';
        canvas.style.height = H + 'px';
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        layoutNodes();
    }

    function layoutNodes() {
        nodes = [];
        edges = [];
        const isMobile = W < 768;
        const cols = isMobile ? 2 : 5;
        const rows = Math.ceil(NODE_LABELS.length / cols);
        const cellW = W / (cols + 1);
        const cellH = H / (rows + 1);

        NODE_LABELS.forEach(function (label, i) {
            var col = i % cols;
            var row = Math.floor(i / cols);
            var baseX = cellW * (col + 1);
            var baseY = cellH * (row + 1);
            nodes.push({
                x: baseX, y: baseY,
                baseX: baseX, baseY: baseY,
                tx: baseX + (Math.random() - 0.5) * cellW * 0.5,
                ty: baseY + (Math.random() - 0.5) * cellH * 0.3,
                wanderAngle: Math.random() * Math.PI * 2,
                wanderSpeed: 0.003 + Math.random() * 0.004,
                wanderRadius: 15 + Math.random() * 25,
                r: isMobile ? 16 : 20,
                label: label,
                glyph: ICON_GLYPHS[i] || '\uf059',
                pulsePhase: Math.random() * Math.PI * 2
            });
        });

        for (var i = 0; i < nodes.length - 1; i++) edges.push({ from: i, to: i + 1 });
        if (nodes.length > 4) edges.push({ from: 0, to: 3 });
        if (nodes.length > 6) edges.push({ from: 3, to: 6 });
        if (nodes.length > 8) edges.push({ from: 7, to: 9 });

        particles = [];
        edges.forEach(function (e, i) {
            for (var j = 0; j < 2; j++) {
                particles.push({
                    edge: i, t: Math.random(),
                    speed: 0.0012 + Math.random() * 0.002,
                    size: 1 + Math.random() * 1,
                    opacity: 0.08 + Math.random() * 0.1
                });
            }
        });
    }

    function drawGrid(colors) {
        ctx.strokeStyle = colors.grid;
        ctx.lineWidth = 0.5;
        var step = 70;
        var x, y;
        for (x = 0; x < W; x += step) {
            ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
        }
        for (y = 0; y < H; y += step) {
            ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
        }
    }

    function drawEdges(colors) {
        edges.forEach(function (e) {
            var a = nodes[e.from], b = nodes[e.to];
            var grad = ctx.createLinearGradient(a.x, a.y, b.x, b.y);
            grad.addColorStop(0, colors.edgeGrad[0]);
            grad.addColorStop(0.5, colors.edgeGrad[1]);
            grad.addColorStop(1, colors.edgeGrad[2]);
            ctx.strokeStyle = grad;
            ctx.lineWidth = 0.7;
            ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();

            ctx.strokeStyle = colors.edgeDash;
            ctx.lineWidth = 0.3;
            ctx.setLineDash([3, 10]);
            ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
            ctx.setLineDash([]);
        });
    }

    function drawParticles(colors) {
        particles.forEach(function (p) {
            p.t += p.speed;
            if (p.t > 1) p.t -= 1;
            var a = nodes[edges[p.edge].from];
            var b = nodes[edges[p.edge].to];
            var x = a.x + (b.x - a.x) * p.t;
            var y = a.y + (b.y - a.y) * p.t;

            var glow = ctx.createRadialGradient(x, y, 0, x, y, p.size * 5);
            glow.addColorStop(0, colors.glowColor + (p.opacity * 0.35) + ')');
            glow.addColorStop(1, colors.glowColor + '0)');
            ctx.fillStyle = glow;
            ctx.beginPath(); ctx.arc(x, y, p.size * 5, 0, Math.PI * 2); ctx.fill();

            ctx.fillStyle = colors.glowColor + p.opacity + ')';
            ctx.beginPath(); ctx.arc(x, y, p.size, 0, Math.PI * 2); ctx.fill();
        });
    }

    function updateNodes(time) {
        nodes.forEach(function (n) {
            n.wanderAngle += (noise(time * 0.00008 + n.pulsePhase * 100) - 0.5) * 0.25;
            n.tx += Math.cos(n.wanderAngle) * n.wanderSpeed * n.wanderRadius;
            n.ty += Math.sin(n.wanderAngle) * n.wanderSpeed * n.wanderRadius;
            var dx = n.baseX - n.tx;
            var dy = n.baseY - n.ty;
            var dist = Math.sqrt(dx * dx + dy * dy);
            var maxDist = n.wanderRadius * 1.5;
            if (dist > maxDist) {
                n.tx += dx * 0.015;
                n.ty += dy * 0.015;
            }
            n.x += (n.tx - n.x) * 0.012;
            n.y += (n.ty - n.y) * 0.012;
        });
    }

    function drawNodes(time, colors) {
        var isMobile = W < 768;
        var fontSize = isMobile ? 7 : 8;

        nodes.forEach(function (n) {
            var dx = mouse.x - n.x;
            var dy = mouse.y - n.y;
            var mouseDist = Math.sqrt(dx * dx + dy * dy);
            var mouseGlow = mouseDist < 180 ? (1 - mouseDist / 180) * 0.12 : 0;
            var pulse = Math.sin(time * 0.0008 + n.pulsePhase) * 0.08 + 0.92;
            var glowR = n.r + 6 + mouseGlow * 12;
            var glow = ctx.createRadialGradient(n.x, n.y, n.r * 0.5, n.x, n.y, glowR);
            glow.addColorStop(0, colors.glowColor + (0.02 * pulse + mouseGlow) + ')');
            glow.addColorStop(1, colors.glowColor + '0)');
            ctx.fillStyle = glow;
            ctx.beginPath(); ctx.arc(n.x, n.y, glowR, 0, Math.PI * 2); ctx.fill();

            ctx.fillStyle = colors.nodeFill;
            if (isLightTheme()) {
                ctx.strokeStyle = colors.nodeStroke;
            } else {
                ctx.strokeStyle = colors.nodeStroke + (0.06 + mouseGlow * 0.15) + ')';
            }
            ctx.lineWidth = 0.8;
            ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2); ctx.fill(); ctx.stroke();

            ctx.fillStyle = colors.nodeIcon + (0.2 + mouseGlow * 0.15) + ')';
            ctx.font = (n.r * 0.6) + 'px "Font Awesome 6 Free"';
            ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
            ctx.fillText(n.glyph, n.x, n.y);

            ctx.fillStyle = colors.nodeLabel + (0.2 + mouseGlow * 0.1) + ')';
            ctx.font = '500 ' + fontSize + 'px Inter, sans-serif';
            ctx.fillText(n.label, n.x, n.y + n.r + 12);
        });
    }

    function draw(time) {
        ctx.clearRect(0, 0, W, H);
        var colors = getThemeColors();
        drawGrid(colors);
        updateNodes(time);
        drawEdges(colors);
        drawParticles(colors);
        drawNodes(time, colors);
        raf = requestAnimationFrame(draw);
    }

    window.addEventListener('resize', function () {
        cancelAnimationFrame(raf);
        resize();
        raf = requestAnimationFrame(draw);
    });
    document.addEventListener('mousemove', function (e) { mouse.x = e.clientX; mouse.y = e.clientY; });
    document.addEventListener('mouseleave', function () { mouse.x = -9999; mouse.y = -9999; });

    // Watch for theme changes
    const observer = new MutationObserver(function () {
        // Colors auto-adapt on next frame via getThemeColors()
    });
    observer.observe(document.body, { attributes: true, attributeFilter: ['class'] });

    resize();
    raf = requestAnimationFrame(draw);
})();
