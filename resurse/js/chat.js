document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.querySelector('.input-container');
    const textarea = document.querySelector('textarea[name="prompt"]');
    const messagesWindow = document.querySelector('.messages-window');
    const typingIndicator = document.getElementById('typing-indicator');

    if (!chatForm) return;

    chatForm.addEventListener('submit', function(event) {
        event.preventDefault();

        const promptText = textarea.value.trim();
        if (!promptText) return;

        textarea.value = '';
        textarea.style.height = 'auto';

        const emptyState = document.querySelector('.empty-state');
        if (emptyState) emptyState.style.display = 'none';

        sendMessage(promptText);
    });

    async function sendMessage(promptText) {
        // B2.4: append an OPTIMISTIC user bubble tagged so we can reconcile it later
        const tempId = `tmp-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
        const optimisticBubble = appendMessage('user', promptText, { tempId, status: 'sending' });

        typingIndicator.style.display = 'flex';
        scrollToBottom();

        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

        try {
            const response = await fetch(window.location.href, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': csrfToken
                },
                body: new URLSearchParams({
                    'prompt': promptText,
                    'csrfmiddlewaretoken': csrfToken
                })
            });

            if (!response.ok) {
                throw new Error(`Server ${response.status}`);
            }

            const data = await response.json();

            // If a brand-new session was just created, sync the URL AND the
            // sidebar so the new chat is renamable/deletable without a reload.
            if (data.session_id) {
                const newUrl = `/chat/${data.session_id}/`;
                if (window.location.pathname !== newUrl) {
                    addNewSessionToSidebar(data.session_id, promptText);
                    window.history.pushState({ path: newUrl }, '', newUrl);
                }
            }

            typingIndicator.style.display = 'none';

            // B2.4: reconcile — the optimistic bubble is now confirmed saved
            optimisticBubble.classList.remove('sending');
            optimisticBubble.classList.add('sent');

            if (data.message && data.message.content) {
                // B3.2 (mockup): fake-stream tokens into the bubble so the UX
                // is ready to swap for EventSource when Branch A ships SSE.
                const bubble = appendMessage('assistant', '');
                await streamInto(bubble, data.message.content);
            }

        } catch (error) {
            console.error("AJAX Error:", error);
            typingIndicator.style.display = 'none';

            // B2.4 + B2.5: mark failed and offer inline retry (promptText kept in closure)
            optimisticBubble.classList.remove('sending');
            optimisticBubble.classList.add('failed');
            attachRetryUI(optimisticBubble, promptText);
        }
    }

    function attachRetryUI(bubble, promptText) {
        const errorRow = document.createElement('div');
        errorRow.className = 'message-error';

        const label = document.createElement('span');
        label.textContent = 'Nu s-a putut trimite.';

        const retryBtn = document.createElement('button');
        retryBtn.type = 'button';
        retryBtn.className = 'retry-btn';
        retryBtn.textContent = 'Încearcă din nou';
        retryBtn.addEventListener('click', () => {
            bubble.remove();
            errorRow.remove();
            sendMessage(promptText);
        });

        errorRow.appendChild(label);
        errorRow.appendChild(retryBtn);
        bubble.insertAdjacentElement('afterend', errorRow);
        scrollToBottom();
    }

    function appendMessage(role, content, { tempId = null, status = null } = {}) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        if (status) messageDiv.classList.add(status);
        if (tempId) messageDiv.dataset.tempId = tempId;

        if (role === 'assistant') {
            const rawHTML = marked.parse(content);
            messageDiv.innerHTML = DOMPurify.sanitize(rawHTML);
        } else {
            messageDiv.textContent = content;
        }

        messagesWindow.insertBefore(messageDiv, typingIndicator);
        scrollToBottom();
        return messageDiv;
    }

    function scrollToBottom() {
        messagesWindow.scrollTop = messagesWindow.scrollHeight;
    }

    // -----------------------------------------------------------------------
    // B3.3 + B3.4: right-click context menu for sidebar sessions (Rename / Șterge)
    // -----------------------------------------------------------------------
    const contextMenu = document.getElementById('session-context-menu');
    let menuTargetItem = null;

    document.querySelectorAll('.session-item').forEach((item) => {
        item.addEventListener('contextmenu', openSessionMenu);
    });

    if (contextMenu) {
        contextMenu.addEventListener('click', (event) => {
            const button = event.target.closest('.context-menu-item');
            if (!button || !menuTargetItem) return;
            const action = button.dataset.action;
            const targetItem = menuTargetItem; // capture before hide nulls it
            hideContextMenu();
            if (action === 'delete') {
                handleDeleteSession(targetItem);
            } else if (action === 'rename') {
                startRenameSession(targetItem);
            }
        });

        document.addEventListener('click', (event) => {
            if (contextMenu.hidden) return;
            if (!contextMenu.contains(event.target)) hideContextMenu();
        });

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && !contextMenu.hidden) hideContextMenu();
        });

        // Re-hide when the user scrolls the sidebar — the menu would otherwise
        // hover in the wrong place.
        document.querySelector('.session-list')?.addEventListener('scroll', hideContextMenu);
    }

    function openSessionMenu(event) {
        if (!contextMenu) return;
        event.preventDefault();
        menuTargetItem = event.currentTarget;

        // Show first so we can measure, then clamp to viewport.
        contextMenu.hidden = false;
        contextMenu.style.left = '0px';
        contextMenu.style.top = '0px';
        const { offsetWidth: w, offsetHeight: h } = contextMenu;
        const x = Math.min(event.clientX, window.innerWidth - w - 4);
        const y = Math.min(event.clientY, window.innerHeight - h - 4);
        contextMenu.style.left = `${x}px`;
        contextMenu.style.top = `${y}px`;
    }

    function hideContextMenu() {
        if (!contextMenu) return;
        contextMenu.hidden = true;
        menuTargetItem = null;
    }

    // Insert a freshly-created session at the top of the sidebar and make it
    // active. Mirrors the server-side template / title-truncation logic so the
    // new row matches a reload-rendered one exactly.
    function addNewSessionToSidebar(sessionId, promptText) {
        const list = document.querySelector('.session-list');
        if (!list) return;

        // De-activate whatever was active before.
        list.querySelectorAll('.session-item.active').forEach((el) => {
            el.classList.remove('active');
            el.dataset.isActive = '0';
        });

        const title = promptText.length > 30
            ? promptText.slice(0, 30) + '...'
            : promptText;

        const row = document.createElement('div');
        row.className = 'session-item active';
        row.dataset.sessionId = String(sessionId);
        row.dataset.isActive = '1';

        const link = document.createElement('a');
        link.href = `/chat/${sessionId}/`;
        link.className = 'session-item-link';
        link.textContent = title;

        row.appendChild(link);
        row.addEventListener('contextmenu', openSessionMenu);

        // Insert right after the "Istoric Recente" header so the newest sits on top.
        const header = list.querySelector('p');
        if (header && header.nextSibling) {
            list.insertBefore(row, header.nextSibling);
        } else {
            list.appendChild(row);
        }
    }

    async function handleDeleteSession(item) {
        const sessionId = item.dataset.sessionId;
        const titleEl = item.querySelector('.session-item-link');
        const title = titleEl ? titleEl.textContent.trim() : 'această conversație';
        const isActive = item.dataset.isActive === '1';

        if (!confirm(`Ștergi „${title}”? Acțiunea nu poate fi anulată.`)) return;

        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

        try {
            const response = await fetch(`/chat/${sessionId}/delete/`, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': csrfToken,
                },
            });
            if (!response.ok) throw new Error(`Server ${response.status}`);

            if (isActive) {
                window.location.href = '/chat/';
                return;
            }
            item.remove();
        } catch (error) {
            console.error('Delete failed:', error);
            alert('Nu am putut șterge conversația. Încearcă din nou.');
        }
    }

    function startRenameSession(item) {
        const link = item.querySelector('.session-item-link');
        if (!link) return;
        const sessionId = item.dataset.sessionId;
        const originalTitle = link.textContent.trim();

        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'session-rename-input';
        input.maxLength = 255;
        input.value = originalTitle;
        input.setAttribute('aria-label', 'Redenumește conversația');

        link.style.display = 'none';
        item.insertBefore(input, link);
        input.focus();
        input.select();

        let resolved = false;
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

        async function commit() {
            if (resolved) return;
            resolved = true;
            const newTitle = input.value.trim();
            if (!newTitle || newTitle === originalTitle) {
                cleanup();
                return;
            }
            try {
                const response = await fetch(`/chat/${sessionId}/rename/`, {
                    method: 'POST',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': csrfToken,
                        'Content-Type': 'application/x-www-form-urlencoded',
                    },
                    body: new URLSearchParams({
                        title: newTitle,
                        csrfmiddlewaretoken: csrfToken,
                    }),
                });
                if (!response.ok) throw new Error(`Server ${response.status}`);
                const data = await response.json();
                link.textContent = data.title || newTitle;
            } catch (error) {
                console.error('Rename failed:', error);
                alert('Nu am putut redenumi conversația.');
            }
            cleanup();
        }

        function cancel() {
            if (resolved) return;
            resolved = true;
            cleanup();
        }

        function cleanup() {
            input.removeEventListener('keydown', onKeydown);
            input.removeEventListener('blur', commit);
            input.remove();
            link.style.display = '';
        }

        function onKeydown(event) {
            if (event.key === 'Enter') {
                event.preventDefault();
                commit();
            } else if (event.key === 'Escape') {
                event.preventDefault();
                cancel();
            }
        }

        input.addEventListener('keydown', onKeydown);
        input.addEventListener('blur', commit);
    }

    // B3.2: stream `fullText` into `bubble` one token at a time, re-rendering
    // markdown each tick. Swap the for-loop for an EventSource onmessage when
    // Branch A's streaming endpoint is live — the rest stays identical.
    async function streamInto(bubble, fullText) {
        bubble.classList.add('streaming');
        const tokens = fullText.split(/(\s+)/); // keep whitespace as its own tokens
        let acc = '';
        for (const token of tokens) {
            acc += token;
            bubble.innerHTML = DOMPurify.sanitize(marked.parse(acc));
            scrollToBottom();
            await new Promise((r) => setTimeout(r, 25));
        }
        bubble.classList.remove('streaming');
    }
});