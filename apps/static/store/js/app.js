/* Alijahon storefront interactions. Progressive enhancement: every form/link still works without JS. */
(() => {
    'use strict';

    const $ = (sel, root = document) => root.querySelector(sel);
    const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
    const I18N = window.APP_I18N || {};
    const t = (key, fallback) => I18N[key] || fallback;

    const formatSum = (value) => `${Math.round(value).toLocaleString('ru-RU').replace(/,/g, ' ')} ${t('currency', "so'm")}`;
    const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));

    function csrfToken() {
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : ($('[name=csrfmiddlewaretoken]') || {}).value;
    }

    async function postForm(url, data) {
        const response = await fetch(url, {
            method: 'POST',
            body: data,
            headers: {'X-CSRFToken': csrfToken(), 'Accept': 'application/json', 'X-Requested-With': 'fetch'},
            credentials: 'same-origin',
        });
        const payload = await response.json().catch(() => ({}));
        if (response.status === 403 && !payload.message) {
            window.location.href = `${document.body.dataset.loginUrl}?next=${encodeURIComponent(location.pathname)}`;
            throw new Error('auth');
        }
        return {ok: response.ok, status: response.status, data: payload};
    }

    const icon = (name, cls = '') => `<svg class="i ${cls}"><use href="#i-${name}"/></svg>`;

    /* ------------------------------------------------------------ toasts */
    const toastRoot = $('.toasts');

    function toast(message, type = 'info', action = null) {
        if (!toastRoot || !message) return;
        const el = document.createElement('div');
        el.className = `toast toast-${type}`;
        el.setAttribute('role', type === 'danger' || type === 'error' ? 'alert' : 'status');
        const glyph = {success: 'check', danger: 'alert', error: 'alert', warning: 'alert'}[type] || 'info';
        el.innerHTML = `<span class="toast-icon">${icon(glyph, 'i-sm')}</span><span>${escapeHtml(message)}</span>` +
            (action ? `<a href="${action.href}">${escapeHtml(action.label)}</a>` : '') +
            `<button class="toast-close" type="button" aria-label="${t('close', 'Yopish')}">${icon('x', 'i-sm')}</button>`;
        toastRoot.appendChild(el);
        const remove = () => {
            el.classList.add('is-leaving');
            setTimeout(() => el.remove(), 250);
        };
        el.querySelector('.toast-close').addEventListener('click', remove);
        setTimeout(remove, action ? 6000 : 4200);
    }

    window.AppToast = toast;
    $$('[data-flash]').forEach((node) => toast(node.dataset.flash, node.dataset.level));

    /* ------------------------------------------------------------ header */
    const header = $('.site-header');
    if (header) {
        const onScroll = () => header.classList.toggle('is-scrolled', window.scrollY > 4);
        onScroll();
        window.addEventListener('scroll', onScroll, {passive: true});
    }

    const mega = $('#mega-menu');
    const megaBackdrop = $('.mega-backdrop');
    const megaToggle = $('[data-mega-toggle]');

    function setMega(open) {
        if (!mega) return;
        mega.classList.toggle('is-open', open);
        megaBackdrop && megaBackdrop.classList.toggle('is-open', open);
        megaToggle && megaToggle.setAttribute('aria-expanded', String(open));
        if (megaBackdrop && header) megaBackdrop.style.top = `${header.getBoundingClientRect().bottom}px`;
    }

    megaToggle && megaToggle.addEventListener('click', () => setMega(!mega.classList.contains('is-open')));
    megaBackdrop && megaBackdrop.addEventListener('click', () => setMega(false));

    /* ------------------------------------------------------------ live search */
    const searchForm = $('[data-search]');
    if (searchForm) {
        const input = $('input', searchForm);
        const panel = $('.search-panel', searchForm);
        let timer = null;
        let controller = null;
        let activeIndex = -1;

        const highlight = (text, query) => {
            const safe = escapeHtml(text);
            const q = query.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            return q ? safe.replace(new RegExp(`(${q})`, 'ig'), '<mark>$1</mark>') : safe;
        };

        const close = () => {
            panel.classList.remove('is-open');
            input.setAttribute('aria-expanded', 'false');
            activeIndex = -1;
        };

        const render = (results, query) => {
            if (!results.length) {
                panel.innerHTML = `<div class="search-empty">${icon('search')}<p class="mt-1">${t('noResults', 'Hech narsa topilmadi')} «${escapeHtml(query)}»</p></div>`;
            } else {
                panel.innerHTML = results.map((item, i) => `
                    <a class="search-item" role="option" id="sr-${i}" href="${item.url}">
                        ${item.image ? `<img src="${item.image}" alt="" loading="lazy" width="48" height="48">` : ''}
                        <span class="grow"><span class="name">${highlight(item.name, query)}</span>
                        <span class="meta">${escapeHtml(item.category)}</span></span>
                        <span class="price">${formatSum(item.price)}</span>
                    </a>`).join('') +
                    `<a class="search-all" href="${searchForm.action}?q=${encodeURIComponent(query)}">${t('allResults', 'Barcha natijalar')} ${icon('arrow-right', 'i-sm')}</a>`;
            }
            panel.classList.add('is-open');
            input.setAttribute('aria-expanded', 'true');
        };

        input.addEventListener('input', () => {
            clearTimeout(timer);
            const query = input.value.trim();
            if (query.length < 2) return close();
            timer = setTimeout(async () => {
                controller && controller.abort();
                controller = new AbortController();
                try {
                    const response = await fetch(`${searchForm.dataset.search}?q=${encodeURIComponent(query)}`,
                        {signal: controller.signal});
                    const data = await response.json();
                    if (input.value.trim() === query) render(data.results || [], query);
                } catch (e) { /* aborted */ }
            }, 180);
        });

        input.addEventListener('keydown', (event) => {
            const items = $$('.search-item', panel);
            if (!panel.classList.contains('is-open') || !items.length) return;
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault();
                activeIndex = (activeIndex + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
                items.forEach((el, i) => el.classList.toggle('is-active', i === activeIndex));
                input.setAttribute('aria-activedescendant', items[activeIndex].id);
            } else if (event.key === 'Enter' && activeIndex >= 0) {
                event.preventDefault();
                window.location.href = items[activeIndex].href;
            }
        });
        input.addEventListener('focus', () => input.value.trim().length >= 2 && panel.innerHTML && panel.classList.add('is-open'));
        document.addEventListener('click', (e) => !searchForm.contains(e.target) && close());
    }

    /* ------------------------------------------------------------ global Esc */
    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape') return;
        setMega(false);
        closeModal();
        $('.filters.is-open') && $('.filters.is-open').classList.remove('is-open');
    });

    /* ------------------------------------------------------------ cart badge + fly animation */
    function updateCartBadges(count) {
        $$('[data-cart-count]').forEach((badge) => {
            badge.textContent = count > 99 ? '99+' : String(count);
            badge.dataset.count = String(count);
            badge.classList.remove('bump');
            void badge.offsetWidth;
            badge.classList.add('bump');
        });
    }

    function flyToCart(sourceImg) {
        const target = $$('[data-cart-target]').find((el) => el.offsetParent !== null);
        if (!sourceImg || !target || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
        const from = sourceImg.getBoundingClientRect();
        const to = target.getBoundingClientRect();
        const dot = document.createElement('div');
        dot.className = 'fly-dot';
        dot.innerHTML = `<img src="${sourceImg.currentSrc || sourceImg.src}" alt="">`;
        dot.style.left = `${from.left + from.width / 2 - 23}px`;
        dot.style.top = `${from.top + from.height / 2 - 23}px`;
        document.body.appendChild(dot);
        requestAnimationFrame(() => {
            dot.style.transform = `translate(${to.left + to.width / 2 - from.left - from.width / 2}px, ${to.top + to.height / 2 - from.top - from.height / 2}px) scale(.3)`;
            dot.style.opacity = '.4';
        });
        setTimeout(() => dot.remove(), 750);
    }

    /* ------------------------------------------------------------ delegated form handlers */
    document.addEventListener('submit', async (event) => {
        const form = event.target;

        if (form.matches('[data-confirm]') && !window.confirm(form.dataset.confirm)) {
            event.preventDefault();
            return;
        }

        if (form.matches('[data-cart-add]')) {
            event.preventDefault();
            const button = form.querySelector('[type=submit]');
            button && button.classList.add('is-loading');
            try {
                const {ok, data} = await postForm(form.action, new FormData(form));
                if (!ok) return toast(data.message || t('error', 'Xatolik yuz berdi'), 'danger');
                updateCartBadges(data.count);
                const card = form.closest('[data-product-card]') || document;
                flyToCart($('img', card));
                toast(data.message, 'success', {href: document.body.dataset.cartUrl, label: t('toCart', "Savatga o'tish")});
                if (button && button.classList.contains('p-add')) {
                    button.classList.add('is-done');
                    button.innerHTML = icon('check');
                    setTimeout(() => {
                        button.classList.remove('is-done');
                        button.innerHTML = icon('plus');
                    }, 1600);
                }
                if (form.dataset.redirect) window.location.href = form.dataset.redirect;
            } catch (e) {
                if (e.message !== 'auth') toast(t('network', "Tarmoq xatosi. Qayta urinib ko'ring."), 'danger');
            } finally {
                button && button.classList.remove('is-loading');
            }
        }

        if (form.matches('[data-like]')) {
            if (document.body.dataset.auth !== '1') return; // fall back to normal POST → login redirect
            event.preventDefault();
            const button = form.querySelector('button');
            try {
                const {ok, data} = await postForm(form.action, new FormData(form));
                if (!ok) return;
                $$(`[data-like-id="${form.dataset.likeId}"] button`).forEach((btn) => {
                    btn.classList.toggle('is-liked', data.liked);
                    btn.setAttribute('aria-pressed', String(data.liked));
                    btn.classList.remove('pop');
                    void btn.offsetWidth;
                    btn.classList.add('pop');
                });
                $$('[data-like-count]').forEach((el) => {
                    el.textContent = data.count;
                    el.dataset.count = data.count;
                });
                toast(data.liked ? t('liked', "Sevimlilarga qo'shildi") : t('unliked', "Sevimlilardan olib tashlandi"),
                    data.liked ? 'success' : 'info');
                if (!data.liked && form.closest('[data-remove-on-unlike]')) {
                    form.closest('[data-product-card]').remove();
                }
            } catch (e) { /* handled */ }
        }

        if (form.matches('[data-submit-once]')) {
            const button = form.querySelector('[type=submit]');
            if (form.dataset.submitted) {
                event.preventDefault();
                return;
            }
            form.dataset.submitted = '1';
            button && button.classList.add('is-loading');
        }
    });

    /* ------------------------------------------------------------ quantity steppers */
    document.addEventListener('click', (event) => {
        const step = event.target.closest('[data-qty-step]');
        if (!step) return;
        const wrap = step.closest('.qty');
        const input = $('input', wrap);
        const min = Number(input.min || 1);
        const max = Number(input.max || 99);
        const value = Math.min(max, Math.max(min, Number(input.value || min) + Number(step.dataset.qtyStep)));
        input.value = value;
        input.dispatchEvent(new Event('change', {bubbles: true}));
        syncQtyButtons(wrap);
    });

    function syncQtyButtons(wrap) {
        const input = $('input', wrap);
        const value = Number(input.value);
        const down = $('[data-qty-step="-1"]', wrap);
        const up = $('[data-qty-step="1"]', wrap);
        if (down) down.disabled = value <= Number(input.min || 1);
        if (up) up.disabled = value >= Number(input.max || 99);
    }

    $$('.qty').forEach(syncQtyButtons);

    /* ------------------------------------------------------------ cart page */
    const cartRoot = $('[data-cart]');
    if (cartRoot) {
        const updateSummary = (data) => {
            $$('[data-cart-subtotal]').forEach((el) => el.textContent = formatSum(data.subtotal));
            $$('[data-cart-gross]').forEach((el) => el.textContent = formatSum(data.subtotal + data.savings));
            $$('[data-cart-savings]').forEach((el) => {
                el.textContent = `− ${formatSum(data.savings)}`;
                el.closest('[data-savings-row]').classList.toggle('hidden', !data.savings);
            });
            $$('[data-cart-items-count]').forEach((el) => el.textContent = data.count);
            updateCartBadges(data.count);
            if (!data.count) window.location.reload();
        };

        let pending = {};
        cartRoot.addEventListener('change', (event) => {
            const input = event.target.closest('[data-cart-qty]');
            if (!input) return;
            const row = input.closest('[data-cart-item]');
            clearTimeout(pending[row.dataset.key]);
            pending[row.dataset.key] = setTimeout(async () => {
                const body = new FormData();
                body.append('key', row.dataset.key);
                body.append('quantity', input.value);
                row.style.opacity = '.6';
                try {
                    const {data} = await postForm(cartRoot.dataset.updateUrl, body);
                    input.value = data.quantity;
                    $('[data-line-total]', row).textContent = formatSum(data.line_total);
                    if (Number(data.quantity) < Number(input.dataset.requested || input.value)) {
                        toast(t('stockLimit', 'Omborda shuncha mavjud'), 'warning');
                    }
                    updateSummary(data);
                } finally {
                    row.style.opacity = '';
                }
            }, 250);
        });

        cartRoot.addEventListener('click', async (event) => {
            const remove = event.target.closest('[data-cart-remove]');
            if (!remove) return;
            event.preventDefault();
            const row = remove.closest('[data-cart-item]');
            const body = new FormData();
            body.append('key', row.dataset.key);
            body.append('action', 'remove');
            row.classList.add('is-removing');
            const {data} = await postForm(cartRoot.dataset.updateUrl, body);
            setTimeout(() => row.remove(), 300);
            updateSummary(data);
        });
    }

    /* ------------------------------------------------------------ modal (quick view) */
    const modal = $('#modal');

    function openModal(html, size = '') {
        if (!modal) return;
        $('.modal-content', modal).innerHTML = html;
        modal.classList.toggle('modal-sm', size === 'sm');
        modal.classList.add('is-open');
        modal.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';
        $$('.qty', modal).forEach(syncQtyButtons);
        const focusTarget = $('[autofocus], .modal-content button, .modal-content a, .modal-content input', modal);
        focusTarget && focusTarget.focus({preventScroll: true});
    }

    function closeModal() {
        if (!modal || !modal.classList.contains('is-open')) return;
        modal.classList.remove('is-open');
        modal.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = '';
    }

    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal || e.target.closest('[data-modal-close]')) closeModal();
        });
    }

    document.addEventListener('click', async (event) => {
        const trigger = event.target.closest('[data-quick-view]');
        if (trigger) {
            event.preventDefault();
            openModal('<div class="quick-view"><div class="qv-media skeleton"></div><div class="qv-info">' +
                '<div class="skeleton sk-line" style="width:40%"></div><div class="skeleton sk-line" style="height:28px;width:85%"></div>' +
                '<div class="skeleton sk-line" style="width:60%"></div><div class="skeleton" style="height:120px"></div></div></div>');
            try {
                const response = await fetch(trigger.dataset.quickView, {headers: {'X-Requested-With': 'fetch'}});
                if (!response.ok) throw new Error();
                openModal(await response.text());
            } catch (e) {
                closeModal();
                window.location.href = trigger.href;
            }
            return;
        }
        const opener = event.target.closest('[data-modal-open]');
        if (opener) {
            event.preventDefault();
            const template = document.getElementById(opener.dataset.modalOpen);
            if (!template) return;
            openModal(template.innerHTML, opener.dataset.modalSize || '');
            const fill = opener.dataset.fill ? JSON.parse(opener.dataset.fill) : {};
            Object.entries(fill).forEach(([name, value]) => {
                const field = $(`[name="${name}"]`, modal);
                if (field) field.value = value;
            });
            Object.entries(fill).forEach(([name, value]) => $$(`[data-text="${name}"]`, modal).forEach((el) => el.textContent = value));
        }
    });

    /* ------------------------------------------------------------ product gallery */
    const gallery = $('[data-gallery]');
    if (gallery) {
        const main = $('.gallery-main', gallery);
        const mainImg = $('img', main);
        $$('.gallery-thumbs button', gallery).forEach((btn) => btn.addEventListener('click', () => {
            $$('.gallery-thumbs button', gallery).forEach((b) => b.classList.toggle('is-active', b === btn));
            mainImg.style.opacity = '0';
            setTimeout(() => {
                mainImg.src = btn.dataset.src;
                mainImg.style.opacity = '1';
            }, 140);
        }));
        if (window.matchMedia('(hover: hover)').matches) {
            main.addEventListener('mousemove', (e) => {
                const rect = main.getBoundingClientRect();
                mainImg.style.transformOrigin = `${((e.clientX - rect.left) / rect.width) * 100}% ${((e.clientY - rect.top) / rect.height) * 100}%`;
            });
            main.addEventListener('mouseenter', () => main.classList.add('is-zooming'));
            main.addEventListener('mouseleave', () => main.classList.remove('is-zooming'));
        } else {
            main.addEventListener('click', () => main.classList.toggle('is-zooming'));
        }
    }

    /* ------------------------------------------------------------ tabs */
    $$('[data-tabs]').forEach((tabs) => {
        const buttons = $$('[role=tab]', tabs);
        buttons.forEach((btn) => btn.addEventListener('click', () => {
            buttons.forEach((b) => {
                const active = b === btn;
                b.classList.toggle('is-active', active);
                b.setAttribute('aria-selected', String(active));
                document.getElementById(b.getAttribute('aria-controls')).hidden = !active;
            });
        }));
        if (location.hash) {
            const target = buttons.find((b) => `#${b.getAttribute('aria-controls')}` === location.hash);
            target && target.click();
        }
    });
    $$('[data-tab-link]').forEach((link) => link.addEventListener('click', () => {
        const btn = $(`[aria-controls="${link.dataset.tabLink}"]`);
        btn && btn.click();
    }));

    /* ------------------------------------------------------------ sticky buy bar */
    const buyBox = $('[data-buy-box]');
    const buyBar = $('.buy-bar');
    if (buyBox && buyBar && 'IntersectionObserver' in window) {
        new IntersectionObserver(([entry]) => buyBar.classList.toggle('is-visible', !entry.isIntersecting && entry.boundingClientRect.top < 0))
            .observe(buyBox);
    }

    /* ------------------------------------------------------------ region → district */
    $$('[data-region-select]').forEach((regionSelect) => {
        const districtSelect = document.getElementById(regionSelect.dataset.regionSelect);
        if (!districtSelect) return;
        const load = async (keep) => {
            const regionId = regionSelect.value;
            districtSelect.disabled = !regionId;
            if (!regionId) return;
            const response = await fetch(`${regionSelect.dataset.url.replace(/0$/, '')}${regionId}`);
            const districts = await response.json();
            const current = keep ? districtSelect.dataset.selected : '';
            districtSelect.innerHTML = `<option value="">${t('chooseDistrict', 'Tumanni tanlang')}</option>` +
                districts.map((d) => `<option value="${d.id}" ${String(d.id) === String(current) ? 'selected' : ''}>${escapeHtml(d.name)}</option>`).join('');
            regionSelect.dispatchEvent(new CustomEvent('districts:loaded', {bubbles: true}));
        };
        regionSelect.addEventListener('change', () => load(false));
        if (regionSelect.value) load(true);
        else districtSelect.disabled = true;
    });

    /* ------------------------------------------------------------ phone mask: +998 (XX) XXX-XX-XX */
    function formatPhone(value) {
        let digits = value.replace(/\D/g, '');
        if (digits.startsWith('998')) digits = digits.slice(3);
        digits = digits.slice(0, 9);
        const parts = [digits.slice(0, 2), digits.slice(2, 5), digits.slice(5, 7), digits.slice(7, 9)];
        let out = '+998';
        if (parts[0]) out += ` (${parts[0]}`;
        if (parts[0].length === 2) out += ')';
        if (parts[1]) out += ` ${parts[1]}`;
        if (parts[2]) out += `-${parts[2]}`;
        if (parts[3]) out += `-${parts[3]}`;
        return out;
    }

    $$('[data-phone]').forEach((input) => {
        if (input.value) input.value = formatPhone(input.value);
        input.addEventListener('focus', () => !input.value && (input.value = '+998 '));
        input.addEventListener('blur', () => input.value.replace(/\D/g, '').length <= 3 && (input.value = ''));
        input.addEventListener('input', () => {
            input.value = formatPhone(input.value);
            input.setCustomValidity('');
        });
        input.form && input.form.addEventListener('submit', (e) => {
            const digits = input.value.replace(/\D/g, '');
            if (input.required && digits.length !== 12) {
                input.setCustomValidity(t('phoneInvalid', "Telefon raqamni to'liq kiriting"));
                input.reportValidity();
                e.preventDefault();
                e.stopImmediatePropagation();
            }
        }, true);
    });

    $$('[data-card-number]').forEach((input) => input.addEventListener('input', () => {
        input.value = input.value.replace(/\D/g, '').slice(0, 16).replace(/(\d{4})(?=\d)/g, '$1 ');
    }));

    /* ------------------------------------------------------------ catalog */
    $$('[data-filters-toggle]').forEach((btn) => btn.addEventListener('click', () => {
        $('.filters').classList.toggle('is-open');
    }));
    $$('[data-autosubmit]').forEach((el) => el.addEventListener('change', () => el.form.submit()));
    $$('[data-price-preset]').forEach((btn) => btn.addEventListener('click', () => {
        const [min, max] = btn.dataset.pricePreset.split('-');
        const form = btn.closest('form');
        form.elements.min_price.value = min || '';
        form.elements.max_price.value = max || '';
        form.submit();
    }));

    const loadMore = $('[data-load-more]');
    if (loadMore) {
        const grid = $(loadMore.dataset.target);
        let busy = false;
        const fetchNext = async () => {
            const next = loadMore.dataset.next;
            if (busy || !next) return;
            busy = true;
            loadMore.classList.add('is-loading');
            const skeletons = Array.from({length: 4}, () => {
                const sk = document.createElement('div');
                sk.className = 'p-card is-skeleton';
                sk.innerHTML = '<div class="p-media skeleton"></div><div class="p-body"><div class="skeleton sk-line" style="width:40%"></div><div class="skeleton sk-line"></div><div class="skeleton sk-line" style="width:60%;height:18px"></div></div>';
                grid.appendChild(sk);
                return sk;
            });
            try {
                const response = await fetch(next, {headers: {'X-Requested-With': 'fetch'}});
                const html = await response.text();
                const doc = new DOMParser().parseFromString(html, 'text/html');
                skeletons.forEach((sk) => sk.remove());
                $$('[data-product-card]', doc).forEach((card) => {
                    card.classList.add('reveal');
                    grid.appendChild(card);
                });
                const meta = $('[data-page-meta]', doc);
                loadMore.dataset.next = meta ? meta.dataset.next : '';
                const shown = grid.querySelectorAll('[data-product-card]').length;
                $$('[data-shown-count]').forEach((el) => el.textContent = shown);
                const bar = $('[data-progress]');
                bar && (bar.style.width = `${Math.min(100, (shown / Number(bar.dataset.total)) * 100)}%`);
                if (!loadMore.dataset.next) loadMore.closest('.load-more-wrap').querySelector('.btn').remove();
                const pager = $('.pagination');
                pager && pager.remove();
            } finally {
                busy = false;
                loadMore.classList.remove('is-loading');
            }
        };
        loadMore.addEventListener('click', (e) => {
            e.preventDefault();
            fetchNext();
        });
    }

    /* ------------------------------------------------------------ rails */
    $$('[data-rail-nav]').forEach((nav) => {
        const rail = document.getElementById(nav.dataset.railNav);
        $$('button', nav).forEach((btn) => btn.addEventListener('click', () => {
            rail.scrollBy({left: Number(btn.dataset.dir) * rail.clientWidth * .9, behavior: 'smooth'});
        }));
    });

    /* ------------------------------------------------------------ copy to clipboard */
    document.addEventListener('click', async (event) => {
        const btn = event.target.closest('[data-copy]');
        if (!btn) return;
        const input = document.getElementById(btn.dataset.copy);
        const value = input ? input.value : btn.dataset.copy;
        try {
            await navigator.clipboard.writeText(value);
        } catch (e) {
            input && input.select();
            document.execCommand('copy');
        }
        toast(t('copied', 'Havola nusxalandi'), 'success');
    });

    /* ------------------------------------------------------------ countdown to midnight */
    $$('[data-countdown]').forEach((root) => {
        const tick = () => {
            const now = new Date();
            const end = new Date(now);
            end.setHours(24, 0, 0, 0);
            const diff = Math.max(0, end - now);
            const values = [diff / 3.6e6, (diff / 6e4) % 60, (diff / 1e3) % 60].map((v) => String(Math.floor(v)).padStart(2, '0'));
            $$('strong', root).forEach((el, i) => el.textContent = values[i]);
        };
        tick();
        setInterval(tick, 1000);
    });

    /* ------------------------------------------------------------ checkout: delivery fee preview */
    const checkout = $('[data-checkout]');
    if (checkout) {
        const tariffs = JSON.parse(checkout.dataset.tariffs);
        const subtotal = Number(checkout.dataset.subtotal);
        const region = $('[name=region]', checkout);
        const refresh = () => {
            const label = (region.options[region.selectedIndex] || {}).text || '';
            const name = label.toLowerCase();
            let fee = null;
            if (region.value) fee = name.includes('shahri') && name.includes('toshkent') ? tariffs.tashkent
                : name.includes('toshkent') ? tariffs.tashkent_region : tariffs.regions;
            $$('[data-delivery-fee]').forEach((el) => el.textContent = fee === null ? t('chooseRegion', 'Viloyatni tanlang')
                : (fee ? formatSum(fee) : t('free', 'Bepul')));
            $$('[data-grand-total]').forEach((el) => el.textContent = formatSum(subtotal + (fee || 0)));
        };
        region.addEventListener('change', refresh);
        refresh();
    }

    /* ------------------------------------------------------------ image upload preview */
    $$('[data-image-preview]').forEach((input) => input.addEventListener('change', () => {
        const file = input.files[0];
        const target = document.getElementById(input.dataset.imagePreview);
        if (!file || !target) return;
        if (file.size > 5 * 1024 * 1024) {
            toast(t('imageTooBig', 'Rasm hajmi 5 MB dan oshmasligi kerak'), 'danger');
            input.value = '';
            return;
        }
        target.innerHTML = `<img src="${URL.createObjectURL(file)}" alt="">`;
        input.form.submit();
    }));
})();
