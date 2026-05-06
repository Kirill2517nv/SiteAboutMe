function gameBoard(config) {
    return {
        sessionId: config.sessionId,
        categories: config.categories,
        boardState: config.boardState,
        players: config.players,

        // Показываем настройку если нет игроков ИЛИ игра ещё не начата (нет отвеченных вопросов)
        setupMode: config.players.length === 0 || Object.keys(config.boardState).length === 0,
        activeQuestion: null,
        showAnswer: false,
        wrongAnswers: [],   // индексы игроков, ответивших неправильно
        saveTimer: null,
        saveError: null,
        newPlayerName: '',

        get allAnswered() {
            return this.categories.length > 0 && this.categories.every(cat =>
                cat.questions.every(q => this.boardState[String(q.id)])
            );
        },

        get allWrong() {
            return this.players.length > 0 && this.wrongAnswers.length >= this.players.length;
        },

        get maxRows() {
            if (!this.categories || this.categories.length === 0) return 0;
            return Math.max(...this.categories.map(c => c.questions.length));
        },

        isAnswered(questionId) {
            return !!this.boardState[String(questionId)];
        },

        hasAnsweredWrong(playerIdx) {
            return this.wrongAnswers.includes(playerIdx);
        },

        openQuestion(question, categoryTitle) {
            if (this.isAnswered(question.id)) return;
            this.activeQuestion = { ...question, categoryTitle };
            this.showAnswer = false;
            this.wrongAnswers = [];
        },

        revealAnswer() {
            this.showAnswer = true;
        },

        markResult(playerIdx, correct) {
            if (playerIdx !== null && playerIdx >= 0 && playerIdx < this.players.length) {
                const delta = correct ? this.activeQuestion.points : -this.activeQuestion.points;
                this.players[playerIdx].score += delta;
            }

            if (correct) {
                // Правильный ответ — закрываем вопрос
                this._closeAndMark();
            } else {
                // Неправильный — добавляем в список и проверяем, все ли уже ответили
                if (!this.wrongAnswers.includes(playerIdx)) {
                    this.wrongAnswers.push(playerIdx);
                }
                // Модал остаётся открытым — ведущий сам решает когда вернуться
            }
        },

        _closeAndMark() {
            this.boardState[String(this.activeQuestion.id)] = true;
            this.activeQuestion = null;
            this.showAnswer = false;
            this.wrongAnswers = [];
            this.scheduleSave();
        },

        skipQuestion() {
            this.boardState[String(this.activeQuestion.id)] = true;
            this.activeQuestion = null;
            this.showAnswer = false;
            this.wrongAnswers = [];
            this.scheduleSave();
        },

        closeModal() {
            this.activeQuestion = null;
            this.showAnswer = false;
            this.wrongAnswers = [];
        },

        addPlayer() {
            const name = this.newPlayerName.trim();
            if (!name) return;
            this.players.push({ name, score: 0 });
            this.newPlayerName = '';
        },

        removePlayer(i) {
            this.players.splice(i, 1);
        },

        startGame() {
            if (this.players.length === 0) {
                this.players.push({ name: 'Игрок 1', score: 0 });
            }
            this.setupMode = false;
            this.scheduleSave();
        },

        resetGame() {
            if (!confirm('Начать заново? Все очки будут сброшены.')) return;
            this.boardState = {};
            this.players.forEach(p => { p.score = 0; });
            this.activeQuestion = null;
            this.showAnswer = false;
            this.wrongAnswers = [];
            this.scheduleSave();
        },

        scheduleSave() {
            clearTimeout(this.saveTimer);
            this.saveTimer = setTimeout(() => this.saveState(), 500);
        },

        async saveState() {
            try {
                const csrfToken = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
                const resp = await fetch(`/games/svoya-igra/session/${this.sessionId}/update/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken,
                    },
                    body: JSON.stringify({
                        board_state: this.boardState,
                        players: this.players,
                        is_active: !this.allAnswered,
                    }),
                });
                this.saveError = resp.ok ? null : 'Ошибка сохранения';
            } catch {
                this.saveError = 'Нет связи с сервером';
            }
        },
    };
}

document.addEventListener('alpine:init', () => {
    Alpine.data('gameBoard', gameBoard);
});
