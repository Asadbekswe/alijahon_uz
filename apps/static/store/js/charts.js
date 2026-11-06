/*
 * Tiny dependency-free SVG charts (bars / line) with a hover crosshair + tooltip and a table view.
 * Usage: <div data-chart='{"type":"bars","labels":[...],"series":[{"name":"…","values":[…]}],"format":"count"}'></div>
 * Colours follow the validated categorical order (slot 1 blue, slot 2 orange); text stays in ink tokens.
 */
(() => {
    'use strict';
    const SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100'];
    const NS = 'http://www.w3.org/2000/svg';
    const el = (name, attrs = {}) => {
        const node = document.createElementNS(NS, name);
        Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
        return node;
    };
    const fmt = (format) => (v) => {
        const n = Math.round(v).toLocaleString('ru-RU').replace(/,/g, ' ');
        return format === 'sum' ? `${n} so'm` : n;
    };
    const short = (v) => v >= 1e6 ? `${+(v / 1e6).toFixed(1)} mln` : v >= 1e3 ? `${+(v / 1e3).toFixed(0)} ming` : String(v);

    function niceMax(max) {
        if (max <= 0) return 4;
        const pow = 10 ** Math.floor(Math.log10(max));
        const step = [1, 2, 2.5, 5, 10].find((s) => s * pow * 4 >= max) * pow;
        return step * 4;
    }

    function render(root) {
        const cfg = JSON.parse(root.dataset.chart);
        const format = fmt(cfg.format);
        const series = cfg.series.map((s, i) => ({...s, color: SERIES[i % SERIES.length]}));
        const n = cfg.labels.length;
        root.innerHTML = '';
        root.classList.add('viz');

        if (series.length > 1) {
            const legend = document.createElement('div');
            legend.className = 'legend';
            series.forEach((s) => {
                const item = document.createElement('span');
                const sw = document.createElement('i');
                sw.style.background = s.color;
                item.append(sw, document.createTextNode(s.name));
                legend.appendChild(item);
            });
            root.appendChild(legend);
        }

        const box = document.createElement('div');
        box.className = 'viz-plot';
        root.appendChild(box);
        const width = Math.max(box.clientWidth, 280);
        const height = Number(cfg.height || 260);
        const pad = {top: 12, right: 8, bottom: 26, left: 54};
        const innerW = width - pad.left - pad.right;
        const innerH = height - pad.top - pad.bottom;
        const max = niceMax(Math.max(0, ...series.flatMap((s) => s.values)));
        const y = (v) => pad.top + innerH - (v / max) * innerH;
        const band = innerW / n;
        const x = (i) => pad.left + band * i + band / 2;

        const svg = el('svg', {width, height, viewBox: `0 0 ${width} ${height}`, role: 'img',
            'aria-label': cfg.title || series.map((s) => s.name).join(', ')});
        // grid + y ticks (recessive)
        for (let t = 0; t <= 4; t++) {
            const value = (max / 4) * t;
            const gy = y(value);
            svg.appendChild(el('line', {x1: pad.left, x2: width - pad.right, y1: gy, y2: gy,
                stroke: t === 0 ? '#d6d2c9' : '#efede7', 'stroke-width': 1}));
            const label = el('text', {x: pad.left - 8, y: gy + 4, 'text-anchor': 'end', 'font-size': 11, fill: '#6b707b'});
            label.textContent = cfg.format === 'sum' ? short(value) : Math.round(value);
            svg.appendChild(label);
        }
        // x labels: at most ~8
        const every = Math.ceil(n / Math.max(2, Math.floor(innerW / 64)));
        cfg.labels.forEach((lab, i) => {
            if (i % every && i !== n - 1) return;
            const text = el('text', {x: x(i), y: height - 8, 'text-anchor': 'middle', 'font-size': 11, fill: '#6b707b'});
            text.textContent = lab;
            svg.appendChild(text);
        });

        if (cfg.type === 'line') {
            series.forEach((s) => {
                const pts = s.values.map((v, i) => `${x(i)},${y(v)}`);
                svg.appendChild(el('path', {d: `M${x(0)},${y(0)} L${pts.join(' L')} L${x(n - 1)},${y(0)} Z`,
                    fill: s.color, 'fill-opacity': .08}));
                svg.appendChild(el('path', {d: `M${pts.join(' L')}`, fill: 'none', stroke: s.color, 'stroke-width': 2,
                    'stroke-linejoin': 'round', 'stroke-linecap': 'round'}));
            });
        } else {
            const groupGap = Math.min(8, band * .25);
            const barW = Math.max(2, (band - groupGap) / series.length - 2);
            series.forEach((s, si) => s.values.forEach((v, i) => {
                if (!v) return;
                const bx = pad.left + band * i + groupGap / 2 + si * (barW + 2);
                const by = y(v);
                const h = y(0) - by;
                const r = Math.min(4, barW / 2, h);
                svg.appendChild(el('path', {
                    d: `M${bx},${y(0)} V${by + r} Q${bx},${by} ${bx + r},${by} H${bx + barW - r} Q${bx + barW},${by} ${bx + barW},${by + r} V${y(0)} Z`,
                    fill: s.color
                }));
            }));
        }

        // hover layer: crosshair + tooltip, snapped to the nearest x
        const hair = el('line', {y1: pad.top, y2: pad.top + innerH, stroke: '#15171c', 'stroke-opacity': .25,
            'stroke-width': 1, visibility: 'hidden'});
        svg.appendChild(hair);
        const dots = series.map((s) => {
            const dot = el('circle', {r: 4.5, fill: s.color, stroke: '#fff', 'stroke-width': 2, visibility: 'hidden'});
            svg.appendChild(dot);
            return dot;
        });
        const hit = el('rect', {x: pad.left, y: pad.top, width: innerW, height: innerH, fill: 'transparent'});
        svg.appendChild(hit);
        box.appendChild(svg);

        const tip = document.createElement('div');
        tip.className = 'viz-tip';
        tip.hidden = true;
        box.appendChild(tip);

        const show = (i) => {
            hair.setAttribute('x1', x(i));
            hair.setAttribute('x2', x(i));
            hair.setAttribute('visibility', 'visible');
            dots.forEach((d, si) => {
                d.setAttribute('cx', x(i));
                d.setAttribute('cy', y(series[si].values[i]));
                d.setAttribute('visibility', cfg.type === 'line' ? 'visible' : 'hidden');
            });
            tip.replaceChildren();
            const head = document.createElement('div');
            head.className = 'viz-tip-head';
            head.textContent = cfg.labels[i];
            tip.appendChild(head);
            series.forEach((s) => {
                const row = document.createElement('div');
                row.className = 'viz-tip-row';
                const sw = document.createElement('i');
                sw.style.background = s.color;
                const strong = document.createElement('strong');
                strong.textContent = format(s.values[i]);
                row.append(sw, strong, document.createTextNode(` ${s.name}`));
                tip.appendChild(row);
            });
            tip.hidden = false;
            const left = Math.min(Math.max(x(i) - tip.offsetWidth / 2, 0), width - tip.offsetWidth);
            tip.style.left = `${left}px`;
        };
        const hide = () => {
            hair.setAttribute('visibility', 'hidden');
            dots.forEach((d) => d.setAttribute('visibility', 'hidden'));
            tip.hidden = true;
        };
        hit.addEventListener('pointermove', (e) => {
            const rect = svg.getBoundingClientRect();
            const i = Math.min(n - 1, Math.max(0, Math.floor((e.clientX - rect.left - pad.left) / band)));
            show(i);
        });
        hit.addEventListener('pointerleave', hide);

        // table view (accessible + exact values)
        const details = document.createElement('details');
        details.className = 'viz-table';
        const summary = document.createElement('summary');
        summary.textContent = root.dataset.tableLabel || 'Jadval ko‘rinishi';
        details.appendChild(summary);
        const table = document.createElement('table');
        table.className = 'table';
        const headRow = table.createTHead().insertRow();
        ['', ...series.map((s) => s.name)].forEach((h) => {
            const th = document.createElement('th');
            th.textContent = h;
            headRow.appendChild(th);
        });
        const body = table.createTBody();
        cfg.labels.forEach((lab, i) => {
            const row = body.insertRow();
            row.insertCell().textContent = lab;
            series.forEach((s) => {
                const cell = row.insertCell();
                cell.className = 'num';
                cell.textContent = format(s.values[i]);
            });
        });
        const wrap = document.createElement('div');
        wrap.className = 'table-wrap';
        wrap.appendChild(table);
        details.appendChild(wrap);
        root.appendChild(details);
    }

    const charts = Array.from(document.querySelectorAll('[data-chart]'));
    charts.forEach(render);
    let timer;
    window.addEventListener('resize', () => {
        clearTimeout(timer);
        timer = setTimeout(() => charts.forEach(render), 150);
    });
})();
