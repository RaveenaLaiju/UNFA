from django.shortcuts import render, redirect
from django.contrib.auth.hashers import make_password, check_password
from django.contrib import messages
from django.db.models import Count
from datetime import date

from .models import User
from user_app.models import (
    Match, Club, Player, Goal, Result,
    Notification, Turf
)


def visitor_home(request):
    """Public homepage - accessible to everyone including visitors."""
    if request.session.get("user_id"):
        return redirect("user_home")
    total_clubs = Club.objects.filter(is_validated=True).count()
    total_players = Player.objects.count()
    today = date.today()

    total_matches = Match.objects.filter(
        match_date__year=today.year,
        match_date__month=today.month
    ).count()

    upcoming_matches = Match.objects.filter(
        match_finished=False,
        match_away_team__isnull=False
    ).order_by('match_date')[:6]

    featured_clubs = Club.objects.filter(is_validated=True)[:6]

    featured_players = Player.objects.select_related(
        'player_club', 'player_position'
    ).order_by('-player_rating')[:6]

    top_scorers = Goal.objects.values(
        'player__player_card_name'
    ).annotate(
        total_goals=Count('goal_id')
    ).order_by('-total_goals')[:5]

    # Auth context for header
    user = None
    is_authenticated = False
    is_manager = False
    is_turf_owner = False
    is_player = False
    unread_count = 0
    notifications = []

    if request.session.get("user_id"):
        try:
            user = User.objects.get(pk=request.session["user_id"], user_active=True)
            is_authenticated = True
            is_manager = Club.objects.filter(club_manager=user, is_validated=True).exists()
            is_turf_owner = Turf.objects.filter(turf_owner=user, is_validated=True).exists()
            is_player = Player.objects.filter(player_user=user).exists()
            notifications = Notification.objects.filter(user=user).order_by("-created_at")[:10]
            unread_count = Notification.objects.filter(user=user, is_read=False).count()
        except User.DoesNotExist:
            pass

    context = {
        'total_clubs': total_clubs,
        'total_players': total_players,
        'total_matches': total_matches,
        'upcoming_matches': upcoming_matches,
        'featured_clubs': featured_clubs,
        'featured_players': featured_players,
        'top_scorers': top_scorers,
        'is_authenticated': is_authenticated,
        'is_visitor': not is_authenticated,
        'is_user': is_authenticated,
        'is_manager': is_manager,
        'is_turf_owner': is_turf_owner,
        'is_player': is_player,
        'user': user,
        'notifications': notifications,
        'unread_count': unread_count,
    }

    return render(request, 'visitor/visitor_home.html', context)


def visitor_sign(request):
    """Sign in / sign up page for visitors."""
    if request.session.get("user_id"):
        return redirect("user_home")

    context = {
        'is_authenticated': False,
        'is_visitor': True,
        'is_user': False,
        'is_manager': False,
        'is_turf_owner': False,
        'is_player': False,
    }
    return render(request, "visitor/visitor_sign.html", context)


def user_login(request):
    """Handle user login with session management."""
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        try:
            accounts = User.objects.get(user_email=email, user_active=True)
            if check_password(password, accounts.user_password):
                request.session["user_id"] = accounts.user_id
                request.session.set_expiry(1209600)

                Notification.objects.create(
                    user=accounts,
                    message=f"Welcome back, {accounts.user_name}! You have successfully logged in.",
                    notification_type='success'
                )

                next_url = request.POST.get("next") or request.GET.get("next")
                # FIX: treat string "None" as empty
                if next_url == "None" or not next_url:
                    next_url = None
                return redirect(next_url or "user_home")
            else:
                messages.error(request, "Invalid password!")
                return render(request, "visitor/visitor_sign.html",
                              {"message": "Invalid password!"})
        except User.DoesNotExist:
            messages.error(request, "Account not found!")
            return render(request, "visitor/visitor_sign.html",
                          {"message": "Could not login!"})

    return render(request, "visitor/visitor_sign.html",
                  {"next": request.GET.get("next")})

def user_registration(request):
    """Handle user registration."""
    if request.method == "POST":
        try:
            table = User()
            table.user_name = request.POST.get("name")
            table.user_age = request.POST.get("age")
            table.user_gender = request.POST.get("gender")
            table.user_email = request.POST.get("email")
            raw_password = request.POST.get("password")
            table.user_password = make_password(raw_password)
            table.save()

            Notification.objects.create(
                user=table,
                message="Welcome to UNFA! Your account has been created successfully.",
                notification_type='success'
            )

            messages.success(request, "User registered successfully! You can Login now!")
            return render(request, "visitor/visitor_sign.html",
                          {"message": "User registered, You can Login now!"})
        except Exception:
            messages.error(request, "Could not register! Please try again.")
            return render(request, "visitor/visitor_sign.html",
                          {"message": "Could not register!"})

    return redirect("visitor_sign")


def matches(request):
    """Public matches page - accessible to all users including visitors."""
    upcoming_matches = Match.objects.filter(
        match_started=False, match_away_team__isnull=False
    ).order_by('match_date')

    finished_matches = Match.objects.filter(
        match_started=True
    ).order_by('-match_date')

    is_authenticated = False
    user = None
    is_manager = False
    is_turf_owner = False
    is_player = False
    unread_count = 0
    notifications = []

    if request.session.get("user_id"):
        try:
            user = User.objects.get(pk=request.session["user_id"], user_active=True)
            is_authenticated = True
            is_manager = Club.objects.filter(club_manager=user, is_validated=True).exists()
            is_turf_owner = Turf.objects.filter(turf_owner=user, is_validated=True).exists()
            is_player = Player.objects.filter(player_user=user).exists()
            notifications = Notification.objects.filter(user=user).order_by("-created_at")[:10]
            unread_count = Notification.objects.filter(user=user, is_read=False).count()
        except User.DoesNotExist:
            pass

    context = {
        'upcoming_matches': upcoming_matches,
        'finished_matches': finished_matches,
        'is_authenticated': is_authenticated,
        'is_visitor': not is_authenticated,
        'is_user': is_authenticated,
        'is_manager': is_manager,
        'is_turf_owner': is_turf_owner,
        'is_player': is_player,
        'user': user,
        'notifications': notifications,
        'unread_count': unread_count,
    }

    return render(request, "visitor/visitor_matches.html", context)
