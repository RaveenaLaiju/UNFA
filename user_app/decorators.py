"""
UNFA - Role-Based Access Control Decorators
Handles permissions for: Visitor, User, Club Manager, Player, Turf Owner
"""
from functools import wraps
from django.shortcuts import redirect,get_object_or_404
from django.contrib import messages
from django.http import HttpResponseForbidden


def login_required_custom(view_func):
    """Custom login required decorator using session-based auth."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.session.get("user_id"):
            messages.error(request, "Please log in to access this page.")
            return redirect("user_login")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def visitor_only(view_func):
    """Only for non-logged-in visitors (redirect if logged in)."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.session.get("user_id"):
            return redirect("user_home")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def user_required(view_func):
    """Any logged-in user (includes club manager, player, turf owner)."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.session.get("user_id"):
            messages.error(request, "Please log in to access this page.")
            return redirect("user_login")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def club_manager_required(view_func):
    """Only club managers (users who own a validated club)."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        from .models import Club

        user_id = request.session.get("user_id")
        if not user_id:
            messages.error(request, "Please log in to access this page.")
            return redirect("user_login")

        if not Club.objects.filter(club_manager_id=user_id, is_validated=True).exists():
            messages.error(request, "Only club managers can access this page.")
            return redirect("user_home")

        return view_func(request, *args, **kwargs)
    return _wrapped_view


def turf_owner_required(view_func):
    """Only turf owners (users who own a validated turf)."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        from .models import Turf

        user_id = request.session.get("user_id")
        if not user_id:
            messages.error(request, "Please log in to access this page.")
            return redirect("user_login")

        if not Turf.objects.filter(turf_owner_id=user_id, is_validated=True).exists():
            messages.error(request, "Only turf owners can access this page.")
            return redirect("user_home")

        return view_func(request, *args, **kwargs)
    return _wrapped_view


def player_required(view_func):
    """Only players (users who have a player card)."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        from .models import Player

        user_id = request.session.get("user_id")
        if not user_id:
            messages.error(request, "Please log in to access this page.")
            return redirect("user_login")

        if not Player.objects.filter(player_user_id=user_id).exists():
            messages.error(request, "Only registered players can access this page.")
            return redirect("user_home")

        return view_func(request, *args, **kwargs)
    return _wrapped_view


def manager_or_owner_required(view_func):
    """Club manager OR turf owner."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        from .models import Club, Turf

        user_id = request.session.get("user_id")
        if not user_id:
            messages.error(request, "Please log in to access this page.")
            return redirect("user_login")

        is_manager = Club.objects.filter(club_manager_id=user_id, is_validated=True).exists()
        is_owner = Turf.objects.filter(turf_owner_id=user_id, is_validated=True).exists()

        if not (is_manager or is_owner):
            messages.error(request, "Only club managers or turf owners can access this page.")
            return redirect("user_home")

        return view_func(request, *args, **kwargs)
    return _wrapped_view


def match_manager_required(view_func):
    """Only the manager of the specific match's home team."""
    @wraps(view_func)
    def _wrapped_view(request, match_id, *args, **kwargs):
        from .models import Match

        user_id = request.session.get("user_id")
        if not user_id:
            messages.error(request, "Please log in to access this page.")
            return redirect("user_login")

        match = get_object_or_404(Match, match_id=match_id)
        if match.match_home_team.club_manager_id != user_id:
            messages.error(request, "Only the home team manager can perform this action.")
            return redirect("club_matches")

        return view_func(request, match_id, *args, **kwargs)
    return _wrapped_view


# ADD THIS NEW DECORATOR
def match_away_manager_required(view_func):
    """Only the manager of the specific match's away team."""
    @wraps(view_func)
    def _wrapped_view(request, match_id, *args, **kwargs):
        from .models import Match

        user_id = request.session.get("user_id")
        if not user_id:
            messages.error(request, "Please log in to access this page.")
            return redirect("user_login")

        match = get_object_or_404(Match, match_id=match_id)
        if match.match_away_team.club_manager_id != user_id:
            messages.error(request, "Only the away team manager can perform this action.")
            return redirect("club_matches")

        return view_func(request, match_id, *args, **kwargs)
    return _wrapped_view