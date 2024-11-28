import os
from collections import OrderedDict
from loguru import logger
import pytz
from threading import Timer

from django.utils import timezone
import backend.common.llm.chat_tools as chat_tools
from backend.common.utils.net_tools import do_result
from backend.common.llm.llm_hub import llm_query
from backend.common.utils.text_tools import get_language_name
from backend.common.user.user import UserManager, DEFAULT_CHAT_LLM_SHOW_COUNT
from backend.settings import LANGUAGE_CODE
from .message import MSG_ROLE
from app_dataforge.prompt import PROMPT_TITLE
from app_dataforge.entry import get_entry_list, add_data
from app_dataforge.models import StoreEntry
from app_dataforge.feature import TITLE_LENGTH

MAX_MESSAGES = 200
MAX_SESSIONS = 1000

class Message:
    def __init__(self, idx, sender, content, created_time):
        self.idx = idx
        self.sender = sender
        self.content = content
        self.created_time = created_time

    def get_raw(self):
        raw = ""
        raw += self.sender + "\n"
        raw += self.content + "\n"
        raw += self.created_time + "\n"
        return raw

    def to_dict(self):
        return {
            "sender": self.sender,
            "content": self.content,
            "created_time": self.created_time
        }


class Session:
    """
    The current session is dynamic and not stored in a database. maybe store it later.
    """
    def __init__(self, sid, user_id, is_group, source, sname = None):
        self.cache = {}
        self.messages = []
        self.chat = None
        self.user_id = user_id
        self.sid = sid
        self.sname = sname
        self.is_group = is_group
        self.source = source
        self.current_content = ""
        self.args = {}
        self.sync_idx = -1
        self.last_chat_time = timezone.now()

    def get_name(self):
        if self.sname is not None:
            return self.sname
        else:
            arr = self.sid.split('_')
            if len(arr) > 1:
                return arr[1][:4] + '-' + arr[1][4:6] + '-' + arr[1][6:8] + ' ' + arr[1][8:10] + ':' + arr[1][10:12] + ':' + arr[1][12:14]                
            return self.sid             
    
    def set_cache(self, key, value):
        self.cache[key] = value

    def get_cache(self, key, default_value=None):
        if key in self.cache:
            return self.cache[key]
        return default_value

    def get_chat_engine(self, model=None, debug=False):
        if model is None:
            model = os.getenv("DEFAULT_CHAT_LLM", chat_tools.DEFAULT_CHAT_LLM)
        if self.chat is None:
            self.chat = {"engine": chat_tools.ChatEngine(model), "model": model}
        elif self.chat["model"] != model:
            if debug:
                logger.info(
                    f"Session {self.sid} model changed from {self.chat['model']} to {model}"
                )
            self.clear_chat()
            self.chat = {"engine": chat_tools.ChatEngine(model), "model": model}
        return self.chat["engine"]

    def load_from_db(self):
        user = UserManager.get_instance().get_user(self.user_id)
        show_count = user.get("llm_chat_show_count", DEFAULT_CHAT_LLM_SHOW_COUNT)
        if isinstance(show_count, str):
            show_count = int(show_count)
    
        self.messages = []
        obj = self.get_item_from_db()
        if obj is not None:
            self.sid = obj["meta"]["sid"]
            self.sname = obj["title"]
            self.is_group = obj["meta"]["is_group"]
            self.source = obj["source"]
            for idx, item in enumerate(obj["meta"]["messages"]):
                self.messages.append(Message(idx, item["sender"], item["content"], item["created_time"]))
            logger.debug(f"load_from_db success, sid {self.sid}, len {len(self.messages)}")
        else:
            logger.warning(f"load_from_db failed, sid {self.sid}")
        self.messages = self.messages[-show_count:]

    def save_to_db(self):
        logger.warning('save_to_db')
        if len(self.messages) == 0:
            return
        obj = self.get_item_from_db()
        messages = [item.to_dict() for item in self.messages]
        if obj is None:
            abstract = self.calc_session_name()
            title = abstract
            if len(abstract) > TITLE_LENGTH:
                title = abstract[:TITLE_LENGTH] + "..."
            dic = {
                "title": title,
                "abstract": abstract,
                "status": "collect",
                "atype": "subjective",
                "user_id": self.user_id,
                "etype": "chat",
                "raw": self.get_raw(),
                "source": self.source,
                "addr": self.sid,
                "meta": {"sid": self.sid, "is_group": self.is_group, 
                        "messages": messages},
            }
            ret, ret_emb, info = add_data(dic)
            logger.info(f"add_data ret {ret}, {ret_emb}, {info}")
        else:
            StoreEntry.objects.filter(
                user_id=self.user_id,
                addr=self.sid
            ).update(
                meta={
                    "sid": self.sid,
                    "is_group": self.is_group,
                    "messages": messages
                },
                raw=self.get_raw()
            )
            logger.info(f"update entry success")
        self.sync_idx = len(self.messages)

    def sync(self):
        if self.sync_idx < len(self.messages):
            self.save_to_db()

    def get_item_from_db(self):
        condition = {"user_id": self.user_id, "etype": "chat", "addr": self.sid}
        fields = [
            "idx",
            "block_id",
            "raw",
            "title",
            "etype",
            "atype",
            "ctype",
            "status",
            "addr",
            "path",
            "source",
            "meta",
            "created_time",
            "updated_time",
        ]
        queryset = get_entry_list(None, condition, 1, fields)
        if queryset is not None and len(queryset) > 0:
            return queryset[0]
        return None

    def get_raw(self):
        arr = []
        for message in self.messages:
            arr.append(message.get_raw())
        return "\n".join(arr)

    @staticmethod
    def create_session(user_id, is_group, source):
        if user_id is None or user_id == "":
            user_id = "tmp"
        sid = user_id + "_" + timezone.now().strftime("%Y%m%d%H%M%S%f")
        return Session(sid, user_id, is_group, source)
    
    def clear_chat(self):
        if self.chat is not None:
            self.chat["engine"].clear_memory()

    def close(self):
        self.save_to_db()
        self.clear_chat()        

    def clear_session(self):
        """
        Clear this session
        """
        StoreEntry.objects.filter(
            user_id=self.user_id, addr=self.sid
        ).delete()
        self.clear_chat()
        self.messages = []

    def get_messages(self, force = False):
        if len(self.messages) == 0 or force:
            self.load_from_db()
        messages = [item.to_dict() for item in self.messages]
        detail = {"type": "text", "content": messages}
        return do_result(True, detail)

    def send_message(self, msg1, msg2):
        created_time = timezone.now().astimezone(pytz.UTC)
        self.add_message("user", msg1, created_time)
        self.add_message("assistant", msg2, created_time)
        if len(self.messages) - self.sync_idx > 10:
            self.save_to_db()

    def add_message(self, sender, content, created_time):
        self.messages.append(Message(len(self.messages), sender, content, created_time.strftime("%Y-%m-%d %H:%M:%S")))
        self.last_chat_time = timezone.now()
        logger.warning(f"after add_messages, len {len(self.messages)}, sid {self.sid}")

    def calc_session_name(self):
        string = ""
        if len(self.messages) == 0:
            return ""
        for item in self.messages:
            if item.sender != "assistant":
                content = item.content
                if len(content) > 100:
                    content = content.strip()
                    content = content[:100] + "..."
                string += content
                string += "\n"
                if len(string) > 500:
                    break
        if len(string) > 0:
            query = PROMPT_TITLE.format(
                content=string, language=get_language_name(LANGUAGE_CODE.lower())
            )
            ret, answer, _ = llm_query(
                self.user_id, MSG_ROLE, query, "chat", debug=False
            )
            if ret:
                return answer
        return ""

class SessionManager:
    __instance = None
    TIMER_INTERVAL = 30 * 60 # 30 minutes

    @staticmethod
    def get_instance():
        if SessionManager.__instance is None:
            SessionManager.__instance = SessionManager()
        return SessionManager.__instance

    def __init__(self):
        self.sessions = OrderedDict()
        self.timer = None
        self.start_timer()

    def check_session_cache(self):
        logger.info("Check session cache")
        current_time = timezone.now()
        sessions_to_remove = []
        
        for sid, session in self.sessions.items():
            time_diff = current_time - session.last_chat_time
            if time_diff.total_seconds() > 3600:  # 3600 second
                session.close()
                sessions_to_remove.append(sid)
            else:
                session.sync()
        
        for sid in sessions_to_remove:
            self.sessions.pop(sid)
            logger.info(f"Removed inactive session: {sid}")

    def start_timer(self):
        self.stop_timer()
        self.timer = Timer(self.TIMER_INTERVAL, self._timer_task)
        self.timer.start()

    def _timer_task(self):
        logger.info("Timer task triggered")
        self.check_session_cache()
        self.start_timer()

    def stop_timer(self):
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None

    def __del__(self):
        self.stop_timer()

    def get_session_by_user(self, user_id, is_group, source):
        logger.info(f'get_session_by_user {user_id}, {is_group}, {source}')
        # get last session from db
        items = StoreEntry.objects.filter(user_id=user_id, etype="chat", source=source).order_by('-updated_time').values("addr", "title", "meta")[:1]
        if len(items) > 0:
            sid = items[0]["addr"]
            if sid not in self.sessions:
                session = Session(sid, user_id, is_group, source)
                session.load_from_db()
                self.add_session(session)

        # get last session
        current_session = None
        most_recent_time = None
        for sid, sess in self.sessions.items():
            if sess.user_id == user_id and sess.source == source:
                if len(sess.messages) == 0:
                    time_str = sid.split('_')[1]
                    # sid: xx_20241128093936091810
                    last_time = timezone.datetime.strptime(
                        time_str,
                        "%Y%m%d%H%M%S%f"
                    ).replace(tzinfo=timezone.get_current_timezone())                    
                else:
                    last_time = timezone.datetime.strptime(
                        sess.messages[-1].created_time,
                        "%Y-%m-%d %H:%M:%S"
                    ).replace(tzinfo=timezone.get_current_timezone())
                if most_recent_time is None or last_time > most_recent_time:
                    most_recent_time = last_time
                    current_session = sess
        
        # check the session is active in 24 hour
        if current_session is not None and most_recent_time is not None:
            time_diff = timezone.now() - most_recent_time
            if time_diff > timezone.timedelta(hours=24):
                current_session.close()
                self.remove_session(current_session.sid)
                current_session = None
        
        if current_session is not None:
            return current_session
            
        return Session.create_session(user_id, is_group, source)
        
    def get_session(self, sid, user_id, is_group, source, force_create=False):
        if force_create:
            return Session.create_session(user_id, is_group, source)
        elif sid == "" or sid is None or sid == 'null':
            return self.get_session_by_user(user_id, is_group, source)
        elif sid in self.sessions:
            session = self.sessions[sid]
        else: # session in db
            session = Session(sid, user_id, is_group, source)
            session.load_from_db()
        self.add_session(session)
        return session
    
    def add_session(self, session):
        if session.sid not in self.sessions:
            if len(self.sessions) >= MAX_SESSIONS:
                oldest_sid, oldest_session = self.sessions.popitem(last=False)
                oldest_session.close()
            self.sessions[session.sid] = session        
        # update visit position
        if session.sid in self.sessions:
            self.sessions.move_to_end(session.sid)

    def remove_session(self, sid):
        if sid in self.sessions:
            self.sessions.pop(sid)
        return True

    def get_sessions(self, user_id):
        """
        Get sessions from a user
        """
        
        slist = []
        items = StoreEntry.objects.filter(user_id=user_id, etype="chat").order_by('-updated_time').values("addr", "title")[0:20]
        sinfo = OrderedDict()
        for item in items:
            if item["addr"] not in sinfo:
                sinfo[item["addr"]] = item["title"]
        
        for session in self.sessions.values():
            if session.user_id == user_id:
                if session.sid not in sinfo:
                    sinfo[session.sid] = session.get_name()

        for sid, sname in sinfo.items():
            if sname == "" or sname is None:
                sname = sid
            slist.append({
                "sid": sid,
                "sname": sname
            })
        detail = {"type": "text", "content": slist}
        logger.debug(f'get_sessions {detail}')
        return do_result(True, detail)        
    
    def send_message(self, msg1:str, msg2:str, sdata: Session):
        need_create_new = False
        if len(sdata.messages) > MAX_MESSAGES:
            need_create_new = True
        if need_create_new:
            sdata.close()
            self.remove_session(sdata.sid)
            sdata = Session.create_session(sdata.user_id, sdata.is_group, sdata.source)
            self.add_session(sdata)
        sdata.send_message(msg1, msg2)
        if sdata.sid in self.sessions:
            self.sessions.move_to_end(sdata.sid)

        logger.warning(f'add_message ret {sdata.sid}')
        return {"type": "json", "content": {"info": msg2, "sid": sdata.sid}}
    
    def clear_session(self, sdata: Session):
        self.remove_session(sdata.sid)
        if sdata is not None:
            sdata.clear_session()
        detail = {"type": "text", "content": 'session cleared'}
        return do_result(True, detail)


def test_chat_manager():
    chat_manager = SessionManager.get_instance()
    x = chat_manager.get_chat_engine("test", "gemini")
    print(x.predict("Hello"))
    x = chat_manager.get_chat_engine("test", chat_tools.DEFAULT_CHAT_LLM)
    print(x.predict("Hello"))


