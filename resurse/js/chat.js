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

            typingIndicator.style.display = 'none';

            // B2.4: reconcile — the optimistic bubble is now confirmed saved
            optimisticBubble.classList.remove('sending');
            optimisticBubble.classList.add('sent');

            if (data.message && data.message.content) {
                appendMessage('assistant', data.message.content);
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
        label.textContent = "Couldn't send.";

        const retryBtn = document.createElement('button');
        retryBtn.type = 'button';
        retryBtn.className = 'retry-btn';
        retryBtn.textContent = 'Try again';
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
});