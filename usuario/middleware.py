from .models import Usuario

class UserInfoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario_id = request.session.get('usuario_id')
        if usuario_id:
            try:
                usuario = Usuario.objects.get(id=usuario_id)
                request.user_is_admin = usuario.es_admin
                request.user_id = usuario.id
            except Usuario.DoesNotExist:
                request.user_is_admin = False
                request.user_id = None
        response = self.get_response(request)
        return response