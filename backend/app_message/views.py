import json
import traceback
from loguru import logger

from django.http import HttpResponse
from rest_framework.views import APIView
from knox.auth import TokenAuthentication
from django.utils.translation import gettext as _

import backend.common.files.filecache as filecache
from backend.common.utils.net_tools import do_result
from backend.common.user.views import LoginView
from backend.common.user.user import DEFAULT_USER
from backend.common.utils.file_tools import get_ext
from .message import *
from .session import SessionManager, get_session_by_req
from rest_framework.permissions import IsAuthenticated
import app_message.agents as agents

class SessionAPIView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        sdata = get_session_by_req(request)
        logger.info(
            f'request.data {request.data}, is_group {sdata.is_group}'
        )

        logger.info(f"message recv: args {sdata.args}")        
        rtype = request.POST.get("rtype", "text")
        try:
            if rtype == "get_messages":
                return sdata.get_messages()
            elif rtype == "clear_session":
                return SessionManager.get_instance().clear_session(sdata)
            elif rtype == "get_sessions":
                return SessionManager.get_instance().get_sessions(sdata.user_id)
            elif rtype == "save_session":
                sdata.save_to_db()
                return do_result(True, {"type": "text", "content": "session saved"})
            elif rtype == "get_current_session":
                detail = {"type": "text", "content": sdata.sid}
                return do_result(True, detail)
        except Exception as e:
            logger.warning(f"message failed {e}")
            traceback.print_exc()
        return HttpResponse(
            json.dumps(
                {"status": "failed", "info": _("backend_processing_failed")}
            )
        )


class MessageAPIView(APIView):
    def post(self, request):
        """
        Accept and process text messages, including URLs
        """
        auth = TokenAuthentication()
        user_auth_tuple = auth.authenticate(request)
        has_token = False
        logger.info(f"user_auth_tuple {user_auth_tuple}")
        if user_auth_tuple is not None:
            request.user, request.auth = user_auth_tuple
            has_token = True

        sdata = get_session_by_req(request)
        logger.info(
            f'request.data {request.data}, has_token {has_token}, is_group {sdata.is_group}'
        )

        if has_token:
            logger.info(f"message recv: args {sdata.args}")            
            rtype = request.POST.get("rtype", "text")
            try:
                if rtype == "text":
                    ret, detail = do_message(sdata)
                    logger.debug(f"{ret}, {detail}")
                    return do_result(ret, detail)
                elif rtype == "file":
                    return self.upload_file(sdata, request)
            except Exception as e:
                logger.warning(f"message failed {e}")
                traceback.print_exc()
            return HttpResponse(
                json.dumps(
                    {"status": "failed", "info": _("backend_processing_failed")}
                )
            )
        elif sdata.is_group: # only in wechat group
            if sdata.args["user_id"] == DEFAULT_USER:
                LoginView.create_user_default()
            rtype = request.POST.get("rtype", "text")
            try:
                if rtype == "text":
                    ret, detail = do_message(sdata)
                    logger.debug(f"{ret}, {detail}")
                    return do_result(ret, detail)
            except Exception as e:
                logger.warning(f"message failed {e}")
                traceback.print_exc()
            return HttpResponse(
                json.dumps(
                    {"status": "failed", "info": _("backend_processing_failed")}
                )
            )
        else:
            content = request.POST.get("content", None)
            if content is None:
                return HttpResponse(
                    json.dumps(
                        {
                            "status": "failed",
                            "info": _("please_sign_up_or_log_in_first"),
                        }
                    )
                )
            ret, detail = agents.UserAgentManager.get_instance().do_command(sdata)
            return HttpResponse(json.dumps({"status": "success", "type":"json", "content":{"info": detail, "sid": sdata.sid}}))

    def upload_file(self, sdata, request):
        ret, path, filename = real_upload_file(request)
        if ret:
            ret, detail = msg_recv_file(
                path, filename, sdata
            )  # May return files or text
            return do_result(True, detail)  # return True to show info
        return HttpResponse(
            json.dumps({"status": "failed", "info": _("backend_processing_failed")})
        )


def real_upload_file(request):
    logger.debug(f"real_upload_file {request.FILES}")
    files = request.FILES
    for file in files.values():  # only one file
        filename = file.name
        tmp_path = filecache.get_tmpfile(get_ext(filename))
        logger.debug(f"file save to {tmp_path}")
        with open(tmp_path, "wb") as f:
            for chunk in file.chunks():
                f.write(chunk)
        return True, tmp_path, filename
    return False, None, None
