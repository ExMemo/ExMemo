import axios from 'axios';
import FormData from 'form-data';
import { getURL, setDefaultAuthHeader } from '@/components/support/conn';
import defaultAvatar from '@/assets/images/chat.png'
import { useI18n } from 'vue-i18n'

export class ChatService {
    constructor(eventBus) {
        this.eventBus = eventBus;
        this.obj = null;
        this.messages = [];
        this.sessions = [];
        const { t } = useI18n();
        this.t = t;
        this.currentUserId = 'user';
        this.currentSessionId = null;
        this.botId = 'assistant';
    }

    async checkSession() {
        if (!this.currentSessionId) {
            await this.getCurrentSession();
            return false;
        }
        return true;
    }

    setObj(obj) {
        this.obj = obj;
    }

    async getCurrentSession(create = false) {
        let info = '';
        this.currentSessionId = null;
        try {
            const formData = new FormData();
            formData.append('rtype', 'get_current_session');
            formData.append('sid', '')
            formData.append('is_group', 'false');
            formData.append('source', 'web');
            formData.append('create', create);
            const func = 'api/message/';
            setDefaultAuthHeader();
            const response = await axios.post(getURL() + func, formData);
            if (response.status === 401) {
                parseBackendError(this.obj, error);
                throw new Error('Token expired');
            }
            info = await this.parseInfo(response);
            this.reloadSessions(info);
        } catch (error) {
            info = String(error);
            this.addMessage(info, this.botId);
        }
    }

    async reloadSessions(sid) {
        this.currentSessionId = sid;
        await this.fetchSessions();
    }

    pushSession(sessionId, sessionName) {
        const newSession =
        {
            roomId: sessionId,
            roomName: sessionName,
            avatar: defaultAvatar,
            users: [
                { _id: this.currentUserId, username: 'user' },
                { _id: this.botId, username: 'assistant' }
            ]
        }
        this.sessions.unshift(newSession);
    }

    async sendMessage(content) {
        let info = '';
        try {
            const formData = new FormData();
            formData.append('rtype', 'text');
            formData.append('content', content.trim());
            formData.append('sid', this.currentSessionId);
            formData.append('source', 'web');
            formData.append('is_group', 'false');

            const func = 'api/message/';
            setDefaultAuthHeader();
            const response = await axios.post(getURL() + func, formData);
            if (response.status === 401) {
                parseBackendError(this.obj, error);
                throw new Error('Token expired');
            }
            const [ret, message, sid] = this.parseMessageReturn(response);
            if (ret === true) {
                info = message;
                if (sid != this.currentSessionId) {
                    await this.reloadSessions(sid);
                }
            } else {
                info = message;
            }
        } catch (error) {
            info = String(error);
        }
        this.addMessage(info, this.botId);
    }

    addMessage(message, userId, dt = null) {
        if (dt === null) {
            const now = new Date();
            dt = now.toISOString().replace('T', ' ').replace(/\.\d+Z/, '');
        }
        let date = dt.split(' ')[0];
        let timestamp = dt.split(' ')[1].slice(0, 5);
        const newMessage = {
            _id: this.messages.length,
            content: message,
            senderId: userId,
            date: date,
            timestamp: timestamp
        };
        this.messages.push(newMessage);
    }

    parseMessageReturn(response) {
        if (response.status === 200) {
            const result = response.data;
            if (result.status === 'success') {
                if (result.type === 'json') {
                    return [true, result.content.info, result.content.sid];
                }
            }
        }
        return [false, this.t('messageSendingFailed'), null]; // later change to i18n
    }

    async parseInfo(response) {
        if (response.status === 200) {
            const result = response.data;
            if (result.status === 'success') {
                if (result.info === null) {
                    return '';
                } else if (typeof result.info === 'string') {
                    return result.info;
                }
            }
        }
        return 'parseInfo failed'; // later change to i18n
    }

    async parseMessages(response) {
        if (response.status === 200) {
            const result = response.data;
            if (result.status === 'success') {
                if (result.info === null) {
                    return;
                } else if (typeof result.info === 'string') {
                    console.log('parseMessages return info', result.info);
                } else if (Array.isArray(result.info)) {
                    this.messages = [];
                    for (const item of result.info) {
                        console.log('item', item);
                        this.addMessage(item.content, item.sender, item.created_time);
                    }
                    this.addDefaultMessage();
                    if (this.eventBus) {
                        this.eventBus.emit('message-updated', this.messages);
                    }    
                }
            }
        }
    }

    async parseSessions(response) {
        if (response.status === 200) {
            const result = response.data;
            if (result.status === 'success') {
                this.sessions = [];
                if (Array.isArray(result.info)) {
                    for (const item of result.info) {
                        this.pushSession(item.sid, item.sname);
                    }
                }
                if (this.eventBus) {
                    this.eventBus.emit('session-updated', this.sessions);
                }
            }
        }
    }

    async fetchSessions() {
        if (await this.checkSession() === false) {
            return;
        }
        try {
            const formData = new FormData();
            formData.append('rtype', 'get_sessions');
            formData.append('sid', this.currentSessionId);
            formData.append('source', 'web');

            const func = 'api/message/';
            setDefaultAuthHeader();
            const response = await axios.post(getURL() + func, formData);
            if (response.status === 401) {
                parseBackendError(this.obj, error);
                throw new Error('Token expired');
            }
            await this.parseSessions(response);
        } catch (error) {
            const error_str = String(error);
            this.addMessage(error_str, this.botId);
        }
    }

    async fetchMessages() {
        try {
            const formData = new FormData();
            formData.append('rtype', 'get_messages');
            formData.append('sid', this.currentSessionId);
            formData.append('source', 'web');

            const func = 'api/message/';
            setDefaultAuthHeader();
            const response = await axios.post(getURL() + func, formData);
            if (response.status === 401) {
                parseBackendError(this.obj, error);
                throw new Error('Token expired');
            }
            await this.parseMessages(response);
        } catch (error) {
            const error_str = String(error);
            this.addMessage(error_str, this.botId);
        }
        this.addDefaultMessage();
    }

    addDefaultMessage() {
        if (this.messages.length === 0) {
            this.addMessage(this.t('letsChat'), this.botId);
        }
    }

    setSession(sessionId) {
        this.currentSessionId = sessionId;
    }

    getCurrentUserId() {
        return this.currentUserId;
    }

    getSessions() {
        return this.sessions;
    }

    getMessages() {
        return this.messages;
    }

    async clearSession() {
        try {
            const formData = new FormData();
            formData.append('rtype', 'clear_session');
            formData.append('sid', this.currentSessionId);
            formData.append('source', 'web');

            const func = 'api/message/';
            setDefaultAuthHeader();
            const response = await axios.post(getURL() + func, formData);
            if (response.status === 401) {
                parseBackendError(this.obj, error);
                throw new Error('Token expired');
            }
            await this.parseInfo(response);
        } catch (error) {
            const error_str = String(error);
            this.addMessage(error_str, this.botId);
        }
        await this.getCurrentSession();
    }

    async newSession() {
        try {
            const formData = new FormData();
            formData.append('rtype', 'save_session');
            formData.append('sid', this.currentSessionId);
            formData.append('source', 'web');

            const func = 'api/message/';
            setDefaultAuthHeader();
            const response = await axios.post(getURL() + func, formData);
            if (response.status === 401) {
                parseBackendError(this.obj, error);
                throw new Error('Token expired');
            }
            await this.parseSessions(response);
        } catch (error) {
            const error_str = String(error);
            this.addMessage(error_str, this.botId);
        }
        await this.getCurrentSession(true);
    }
}