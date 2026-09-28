from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Sum, Count, Max, Value
from django.db.models.functions import Coalesce
from django.utils.timezone import now
from django.contrib import messages
from django.conf import settings
from django.utils.text import slugify
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation
from itertools import chain,combinations
from operator import attrgetter
import os
import re
from django.utils import timezone
from datetime import date, timedelta
import random
import razorpay
from django.views.decorators.http import require_POST
from visitor_app.models import User
from datetime import datetime, time as dt_time
from django.urls import reverse
from django.db.models import Prefetch
from django.db import transaction

from .decorators import (
    login_required_custom, user_required, club_manager_required,
    turf_owner_required, player_required, manager_or_owner_required,
    match_manager_required,match_away_manager_required
)
from .models import *


def _get_turf_owner_context(request, user, active_tab='dashboard', selected_turf=None):
    """Build unified context for turf owner dashboard."""
    owned_turfs = Turf.objects.filter(turf_owner=user, is_validated=True)
    all_bookings = Booking.objects.filter(turf__in=owned_turfs).order_by(
        "-booking_date", "-time_slot__tt_time__time_range"
    )

    # Stats
    pending_count = all_bookings.filter(status="Pending").count()
    paid_bookings = all_bookings.filter(is_paid=True)
    total_earnings = paid_bookings.aggregate(total=Sum('turf__turf_rate'))['total'] or 0

    now = timezone.now()
    monthly_earnings = paid_bookings.filter(
        booking_date__year=now.year,
        booking_date__month=now.month
    ).aggregate(total=Sum('turf__turf_rate'))['total'] or 0

    pending_payments = all_bookings.filter(
        status="Accepted", is_paid=False
    ).aggregate(total=Sum('turf__turf_rate'))['total'] or 0

    total_transactions = paid_bookings.count()

    # Payments list (using paid bookings as payment records)
    payments = paid_bookings.select_related('turf', 'customer')[:50]

    # Notifications
    Notification.objects.filter(user=user, is_read=False).update(is_read=True)
    notifications = Notification.objects.filter(user=user).order_by("-created_at")
    unread_count = notifications.filter(is_read=False).count()

    # Update turf context
    time_slots = []
    time_map = []
    error = None

    if selected_turf and selected_turf.is_validated:
        registered_time_ids = Turf_time_map.objects.filter(
            tt_turf=selected_turf
        ).values_list('tt_time__time_id', flat=True)
        time_slots = Time_Schedule.objects.exclude(time_id__in=registered_time_ids)
        time_map = Turf_time_map.objects.filter(tt_turf=selected_turf).select_related('tt_time')
    elif selected_turf and not selected_turf.is_validated:
        error = "This turf is pending validation and cannot be updated yet."

    context = {
        "user": user,
        "owned_turfs": owned_turfs,
        "bookings": all_bookings,
        "pending_count": pending_count,
        "total_earnings": total_earnings,
        "monthly_earnings": monthly_earnings,
        "pending_payments": pending_payments,
        "total_transactions": total_transactions,
        "payments": payments,
        "turf": selected_turf,
        "time_slots": time_slots,
        "time_map": time_map,
        "error": error,
        "active_tab": active_tab,
        "notifications": notifications[:10],
        "unread_count": unread_count,
    }
    context.update(get_user_role_context(request))
    return context

def user_acc(request):
    """Get the currently logged-in user from session."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    try:
        return User.objects.get(pk=user_id, user_active=True)
    except User.DoesNotExist:
        return None


def check_manager(request):
    """Check if current user is a club manager."""
    user = user_acc(request)
    if not user:
        return False
    return Club.objects.filter(club_manager=user, is_validated=True).exists()


def check_turf_owner(request):
    """Check if current user is a turf owner."""
    user = user_acc(request)
    if not user:
        return False
    return Turf.objects.filter(turf_owner=user, is_validated=True).exists()


def check_player(request):
    """Check if current user is a registered player."""
    user = user_acc(request)
    if not user:
        return False
    return Player.objects.filter(player_user=user).exists()


def get_user_role_context(request):
    """Get user role context for templates. Includes notifications for header."""
    user = user_acc(request)
    if not user:
        return {
            'is_authenticated': False,
            'is_visitor': True,
            'is_user': False,
            'is_manager': False,
            'is_turf_owner': False,
            'is_player': False,
            'player_id': None,
            'notifications': [],
            'unread_count': 0,
            'my_club': None,          
        }

    player = Player.objects.filter(player_user=user).first()
    player_id = player.player_id if player else None

    # Fetch the user's own validated club once for navbar links
    my_club = Club.objects.filter(club_manager=user, is_validated=True).first()

    unread_count = Notification.objects.filter(user=user, is_read=False).count()
    notifications = Notification.objects.filter(user=user).order_by("-created_at")[:50]

    return {
        'is_authenticated': True,
        'is_visitor': False,
        'is_user': True,
        'is_manager': my_club is not None,
        'is_turf_owner': check_turf_owner(request),
        'is_player': check_player(request),
        'user': user,
        'player_id': player_id,
        'notifications': notifications,
        'unread_count': unread_count,
        'my_club': my_club,          # <-- add this
    }

def create_notification(user, message, notification_type='info'):
    """Helper to create notifications with type."""
    return Notification.objects.create(
        user=user,
        message=message,
        notification_type=notification_type
    )



@login_required_custom
def user_home(request):
    """User dashboard - accessible to all logged-in users."""
    user = user_acc(request)

    # Mark all as read when visiting dashboard
    Notification.objects.filter(user=user, is_read=False).update(is_read=True)

    clubs = Club.objects.filter(club_manager=user, is_validated=True)
    turfs = Turf.objects.filter(turf_owner=user, is_validated=True)
    playerss = Player.objects.filter(player_user=user)

    club = clubs.first()

    players = Player.objects.filter(player_club=club) if club else []
    matches = Match.objects.filter(Q(match_home_team=club) | Q(match_away_team=club)) if club else []
    bookings = Booking.objects.filter(customer=user) if club else []

    # Landing page stats for gaming template
    today = date.today()
    total_clubs = Club.objects.filter(is_validated=True).count()
    total_players = Player.objects.count()
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
    
        # ── Tournament data ──
    today = date.today()
    active_tournaments_qs = Tournament.objects.filter(is_active=True, is_completed=False)
    active_tournaments_count = active_tournaments_qs.count()

    upcoming_raw = Tournament.objects.filter(
        t_date__gte=today, is_active=True, is_completed=False
    ).order_by('t_date')[:6]

    # Attach spots_remaining so templates don't do math
    upcoming_tournaments = []
    for t in upcoming_raw:
        t.spots_remaining = t.max_teams - (t.registered_teams_count or 0)
        upcoming_tournaments.append(t)

    past_tournaments_count = Tournament.objects.filter(
        Q(is_completed=True) | Q(t_date__lt=today)
    ).count()

    total_prize_pool = active_tournaments_qs.aggregate(total=Sum('prize_pool'))['total'] or 0
    total_tournament_teams = T_club_map.objects.filter(
        t_c_tournament__in=active_tournaments_qs, is_paid=True
    ).count()

    finished_tournament_matches = Match.objects.filter(
        tournament__isnull=False, match_finished=True
    ).count()

    my_registrations = []
    if club:
        my_registrations = list(T_club_map.objects.filter(
            t_c_club=club
        ).values_list('t_c_tournament_id', flat=True))

    context = {
        "user": user,
        "clubs": clubs,
        "turfs": turfs,
        "club": club,
        "players": players,
        "playerss": playerss,
        "matches": matches,
        "bookings": bookings,
        "MIN_PLAYERS": 6,
        "is_manager": bool(club),
        # Landing page stats
        "total_clubs": total_clubs,
        "total_players": total_players,
        "total_matches": total_matches,
        "upcoming_matches": upcoming_matches,
        "featured_clubs": featured_clubs,
        "featured_players": featured_players,
        "top_scorers": top_scorers,
        # Pending banners
        "has_pending_turf":   Turf.objects.filter(turf_owner=user, is_validated=False).exists(),
        "has_pending_club":   Club.objects.filter(club_manager=user, is_validated=False).exists(),
        "has_pending_player": Player.objects.filter(player_user=user).exists(),
        "show_player_card":   not Player.objects.filter(player_user=user).exists() and not Turf.objects.filter(turf_owner=user).exists(),
        "show_register_club": not Club.objects.filter(club_manager=user).exists() and not Turf.objects.filter(turf_owner=user).exists(),
        "show_register_turf": not Turf.objects.filter(turf_owner=user).exists() and not Club.objects.filter(club_manager=user).exists() and not Player.objects.filter(player_user=user).exists(),
        "active_tournaments_count": active_tournaments_count,
        "upcoming_tournaments": upcoming_tournaments,
        "past_tournaments_count": past_tournaments_count,
        "total_prize_pool": total_prize_pool,
        "total_tournament_teams": total_tournament_teams,
        "finished_tournament_matches": finished_tournament_matches,
        "my_registrations": my_registrations,
    }
    context.update(get_user_role_context(request))
    return render(request, "user/user_home.html", context)


@login_required_custom
def user_logout(request):
    """Handle user logout."""
    user = user_acc(request)
    if user:
        create_notification(
            user,
            "You have been logged out successfully.",
            'info'
        )
    request.session.flush()
    messages.success(request, "You have been logged out successfully.")
    return redirect("visitor_home")


@login_required_custom
def my_card(request):
    """Player card page - accessible to all logged-in users."""
    user = user_acc(request)

    player_card = Player.objects.filter(player_user=user.user_id).first()
    positions = Position.objects.all()

    user_name = user.user_name
    is_long = len(user_name) > 16
    suggestions = generate_short_names(user_name) if is_long else []

    club = player_card.player_club if player_card else None

    current_club_matches = 0
    if club:
        current_club_matches = Match.objects.filter(
            Q(match_home_team=club) | Q(match_away_team=club),
            match_finished=True
        ).count()

    context = {
        "user": user,
        "player_card": player_card,
        "positions": positions,
        "suggestions": suggestions,
        "is_long": is_long,
        "club": club,
        "current_club_matches": current_club_matches,
    }
    context.update(get_user_role_context(request))

    return render(request, "user/my_card.html", context)


@login_required_custom
def view_players(request):
    """View all players - accessible to all logged-in users."""
    user = user_acc(request)
    clubs = Club.objects.filter(club_manager=user, is_validated=True)

    name_filter = request.GET.get("searchName", "").strip().lower()
    district_filter = request.GET.get("searchDistrict", "").strip().lower()
    position_filter = request.GET.get("filterPosition", "")
    sort_rating = request.GET.get("sortRating", "")
    recruit_filter = request.GET.get("filterRecruit", "")

    players = Player.objects.select_related(
        "player_user", "player_position", "player_club"
    ).annotate(
        total_goals=Count("goal"),
        total_assists=Count("assist"),
        total_saves=Count("save"),
    )

    if name_filter:
        players = players.filter(player_card_name__icontains=name_filter)
    if district_filter:
        players = players.filter(player_district__icontains=district_filter)
    if position_filter:
        players = players.filter(player_position__position_code=position_filter)
    if recruit_filter == "available":
        players = players.filter(player_club__isnull=True)
    elif recruit_filter == "assigned":
        players = players.filter(player_club__isnull=False)

    if sort_rating == "high":
        players = players.order_by("-player_rating")
    elif sort_rating == "low":
        players = players.order_by("player_rating")
    else:
        players = players.order_by("-player_id")

    current_user = request.session["user_id"]
    club = Club.objects.filter(club_manager=current_user, is_validated=True).first()
    is_manager = club is not None

    if club:
        request.session["current_club"] = club.club_id

    context = {
        "players": players,
        "positions": Position.objects.all(),
        "is_manager": is_manager,
        "club": club,
        "clubs": clubs,
    }
    context.update(get_user_role_context(request))

    return render(request, "user/players.html", context)


@player_required
def view_player_profile(request, player_id):
    """View player profile - accessible to all logged-in users."""
    player = Player.objects.select_related(
        "player_position", "player_club", "player_user"
    ).get(player_id=player_id)

    total_goals = Goal.objects.filter(player=player).count()
    total_assists = Assist.objects.filter(player=player).count()
    total_saves = Save.objects.filter(player=player).count()

    match_ids = set()
    match_ids.update(
        Goal.objects.filter(player=player).values_list("result__result_match", flat=True)
    )
    match_ids.update(
        Assist.objects.filter(player=player).values_list("result__result_match", flat=True)
    )
    match_ids.update(
        Save.objects.filter(player=player).values_list("result__result_match", flat=True)
    )

    matches = Match.objects.filter(match_id__in=match_ids).order_by("-match_date")

    positions = Position.objects.all()

    context = {
        "player": player,
        "matches": matches,
        "total_goals": total_goals,
        "total_assists": total_assists,
        "total_saves": total_saves,
        "positions": positions,  
    }
    context.update(get_user_role_context(request))

    return render(request, "user/view_player_profile.html", context)


@login_required_custom
def player_public_profile(request, player_id):

    player = get_object_or_404(
        Player.objects.select_related(
            "player_user",
            "player_position",
            "player_club",
        ),
        player_id=player_id,
    )

    player_user = player.player_user
    club = player.player_club

    # ==========================================================
    # PLAYER GOALS
    # ==========================================================

    goals = (
        Goal.objects.filter(
            player=player
        )
        .select_related(
            "result",
            "result__result_match",
            "for_club",
        )
        .order_by("-time")
    )

    total_goals = goals.count()

    # ==========================================================
    # PLAYER ASSISTS
    # ==========================================================

    assists = (
        Assist.objects.filter(
            player=player
        )
        .select_related(
            "result",
            "result__result_match",
            "for_club",
        )
        .order_by("-time")
    )

    total_assists = assists.count()

    # ==========================================================
    # PLAYER SAVES
    # ==========================================================

    saves = (
        Save.objects.filter(
            player=player
        )
        .select_related(
            "result",
            "result__result_match",
            "for_club",
        )
        .order_by("-time")
    )

    total_saves = saves.count()

    # ==========================================================
    # TOTAL ACTIONS
    # ==========================================================

    total_actions = (
        total_goals
        + total_assists
        + total_saves
    )

    home_matches = player.home_squad.all()
    away_matches = player.away_squad.all()

    # ==========================================================
    # ALL MATCHES
    # ==========================================================

    player_matches = (
        home_matches
        .union(away_matches)
    )

    total_matches = player_matches.count()

    # ==========================================================
    # COMPLETED MATCHES
    # ==========================================================

    recent_matches = (
        player.home_squad.filter(
            match_finished=True
        )
        .union(
            player.away_squad.filter(
                match_finished=True
            )
        )
        .order_by(
            "-match_date",
            "-match_time"
        )
    )

    finished_matches = recent_matches.count()

    # ==========================================================
    # UPCOMING / LIVE MATCHES
    # ==========================================================

    upcoming_player_matches = (
        player.home_squad.filter(
            match_finished=False
        )
        .union(
            player.away_squad.filter(
                match_finished=False
            )
        )
        .order_by(
            "match_date",
            "match_time"
        )
    )

    upcoming_matches = upcoming_player_matches.count()


    current_user = user_acc(request)

    # ==========================================================
    # PLAYER ROLE
    # ==========================================================

    is_player = False

    if current_user:
        is_player = (
            player.player_user_id == current_user.pk
        )

    # ==========================================================
    # MANAGER INFORMATION
    # ==========================================================

    managed_clubs = Club.objects.none()
    is_manager = False

    if current_user:

        managed_clubs = (
            Club.objects.filter(
                club_manager=current_user
            )
            .select_related(
                "club_home_ground"
            )
        )

        is_manager = managed_clubs.exists()

    # ==========================================================
    # IS CURRENT USER THE MANAGER OF THIS PLAYER'S CLUB?
    # ==========================================================

    manager_owns_player_club = False
    is_current_club_manager = False
    is_club_manager = False

    if current_user and club:

        manager_owns_player_club = (
            Club.objects.filter(
                club_manager=current_user,
                club_id=club.club_id,
            ).exists()
        )

        is_current_club_manager = (
            manager_owns_player_club
        )

        is_club_manager = (
            manager_owns_player_club
        )

    # ==========================================================
    # CLUB MANAGER
    # ==========================================================

    club_manager = None

    if club:
        club_manager = club.club_manager

    # ==========================================================
    # CONTEXT
    # ==========================================================

    context = {

        # ------------------------------------------------------
        # PLAYER
        # ------------------------------------------------------

        "player": player,
        "player_user": player_user,

        # ------------------------------------------------------
        # CLUB
        # ------------------------------------------------------

        "club": club,
        "club_manager": club_manager,

        # ------------------------------------------------------
        # GOALS
        # ------------------------------------------------------

        "goals": goals,
        "total_goals": total_goals,

        # ------------------------------------------------------
        # ASSISTS
        # ------------------------------------------------------

        "assists": assists,
        "total_assists": total_assists,

        # ------------------------------------------------------
        # SAVES
        # ------------------------------------------------------

        "saves": saves,
        "total_saves": total_saves,

        # ------------------------------------------------------
        # TOTAL ACTIONS
        # ------------------------------------------------------

        "total_actions": total_actions,

        # ------------------------------------------------------
        # MATCHES
        # ------------------------------------------------------

        "total_matches": total_matches,
        "finished_matches": finished_matches,
        "recent_matches": recent_matches,

        "upcoming_matches": upcoming_matches,
        "upcoming_player_matches": upcoming_player_matches,

        # ------------------------------------------------------
        # PLAYER / MANAGER ROLES
        # ------------------------------------------------------

        "is_player": is_player,

        "is_manager": is_manager,

        "managed_clubs": managed_clubs,

        "is_current_club_manager": is_current_club_manager,

        "is_club_manager": is_club_manager,

        "manager_owns_player_club": manager_owns_player_club,
    }


    context.update(
        get_user_role_context(request)
    )

    return render(
        request,
        "user/player_public_profile.html",
        context
    )
    
@login_required_custom
def user_clubs(request):
    """View all clubs - accessible to all logged-in users."""
    clubs = Club.objects.filter(is_validated=True)
    updated_clubs = []

    for club in clubs:
        club.club_weight = calculate_club_power(club.club_id)
        club.save()
        updated_clubs.append(club)

    updated_clubs.sort(key=lambda x: x.club_weight, reverse=True)

    is_player = False
    user = user_acc(request)
    if user:
        is_player = Player.objects.filter(player_user=user).exists()

    context = {
        "clubs": updated_clubs,
        "is_manager": check_manager(request),
        "is_player": is_player,
    }
    context.update(get_user_role_context(request))

    return render(request, "user/clubs.html", context)


@login_required_custom
def club_details(request, club_id):
    """View club details - accessible to all logged-in users."""
    club = get_object_or_404(Club, club_id=club_id, is_validated=True)
    players = Player.objects.filter(player_club=club)
    matches = Match.objects.filter(
        Q(match_home_team=club) | Q(match_away_team=club),
        match_finished=True
    ).order_by('-match_date')

    for match in matches:
        match.result = Result.objects.filter(result_match=match).first()

    context = {
        "club": club,
        "players": players,
        "matches": matches,
        "is_manager": check_manager(request)
    }
    context.update(get_user_role_context(request))

    return render(request, "user/club_details.html", context)

@login_required_custom
def watch_matches(request):

    current_time = timezone.now()

    match_queryset = (
        Match.objects
        .select_related(
            "match_home_team",
            "match_away_team",
            "match_turf",
            "tournament",
        )
    )

    upcoming_matches = (
        match_queryset
        .filter(
            match_started=False,
            match_finished=False,
            match_away_team__isnull=False,
        )
        .order_by(
            "match_date",
            "match_time",
        )
    )

    live_matches = (
        match_queryset
        .filter(
            match_started=True,
            match_finished=False,
            match_away_team__isnull=False,
        )
        .order_by(
            "match_date",
            "match_time",
        )
    )

    finished_matches = (
        match_queryset
        .filter(
            match_finished=True,
            match_away_team__isnull=False,
        )
        .order_by(
            "-match_finished_at",
            "-match_date",
            "-match_time",
        )
    )

    all_matches = list(
        upcoming_matches
    ) + list(
        live_matches
    ) + list(
        finished_matches
    )

    result_map = {
        result.result_match_id: result
        for result in Result.objects.filter(
            result_match__in=all_matches
        )
    }

    for match in all_matches:
        match.result = result_map.get(match.match_id)

    context = {
        "upcoming_matches": upcoming_matches,
        "live_matches": live_matches,
        "finished_matches": finished_matches,
        "now": current_time,
    }

    context.update(
        get_user_role_context(request)
    )

    return render(
        request,
        "user/watch_matches.html",
        context,
    )

    
def generate_short_names(full_name):
    """Generate various short name suggestions."""
    parts = full_name.split()

    if len(parts) == 1:
        return [full_name]

    first_name = parts[0]
    last_name = parts[-1]
    first_initial = first_name[0]
    last_initial = last_name[0]

    short_names = [
        first_name,
        last_name,
        f"{first_initial}. {last_name}",
        f"{first_name} {last_initial}.",
        f"{first_initial}{last_name}",
        f"{first_initial}.{last_initial}.",
    ]

    return short_names


def calculate_player_power(gender: str, age: int, height: int, weight: int, strong_foot: str) -> int:
    """Improved player power calculation with smooth scaling."""
    power = 50

    if gender.lower() == "male":
        power += 2
    elif gender.lower() == "female":
        power -= 2

    if 24 <= age <= 28:
        power += 12
    elif 20 <= age < 24 or 28 < age <= 32:
        power += 8
    elif 17 <= age < 20 or 32 < age <= 36:
        power += 4
    else:
        power -= 5

    if height >= 190:
        power += 8
    elif 178 <= height < 190:
        power += 6
    elif 165 <= height < 178:
        power += 4
    else:
        power += 1

    bmi = weight / ((height / 100) ** 2)
    if 21 <= bmi <= 24:
        power += 10
    elif 18.5 <= bmi < 21 or 24 < bmi <= 27:
        power += 6
    elif 17 <= bmi < 18.5 or 27 < bmi <= 30:
        power += 2
    else:
        power -= 6

    if strong_foot.lower() == "both":
        power += 6
    elif strong_foot.lower() in ["left", "right"]:
        power += 2

    power = max(40, min(power, 100))
    return round(power)


def calculate_club_power(club_id):
    """Calculate club power based on various factors."""
    club = get_object_or_404(Club, club_id=club_id, is_validated=True)

    total_rating = Player.objects.filter(player_club=club).aggregate(
        total=Coalesce(Sum("player_rating"), Value(0))
    )["total"]

    player_count = Player.objects.filter(player_club=club).count()
    if player_count > 0:
        avg_rating = total_rating / player_count
    else:
        avg_rating = 0

    team_strength_score = avg_rating * 10

    matches = Match.objects.filter(
        Q(match_home_team=club) | Q(match_away_team=club),
        match_finished=True
    )

    wins = draws = losses = 0

    for match in matches:
        result = Result.objects.filter(result_match=match).first()
        if not result:
            continue

        if match.match_home_team == club:
            my_score = result.result_home_team
            opp_score = result.result_away_team
        else:
            my_score = result.result_away_team
            opp_score = result.result_home_team

        if my_score > opp_score:
            wins += 1
        elif my_score == opp_score:
            draws += 1
        else:
            losses += 1

    total_matches = matches.count()

    if total_matches > 0:
        total_points = (wins * 3) + (draws * 1)
        max_points = total_matches * 3
        performance_ratio = total_points / max_points
    else:
        performance_ratio = 0

    performance_score = performance_ratio * 1000
    squad_score = min(player_count * 20, 1000)
    experience_score = min(total_matches * 30, 1000)

    club_power = (
        (team_strength_score * 0.4) +
        (performance_score * 0.3) +
        (squad_score * 0.15) +
        (experience_score * 0.15)
    )

    return round(club_power)


def calculate_player_rating(player):
    """Stable player rating calculation without feedback loops."""
    goals = Goal.objects.filter(player=player).count()
    assists = Assist.objects.filter(player=player).count()
    saves = Save.objects.filter(player=player).count()

    match_ids = set()
    match_ids.update(
        Goal.objects.filter(player=player).values_list("result__result_match", flat=True)
    )
    match_ids.update(
        Assist.objects.filter(player=player).values_list("result__result_match", flat=True)
    )
    match_ids.update(
        Save.objects.filter(player=player).values_list("result__result_match", flat=True)
    )

    matches_played = len(match_ids)
    if matches_played == 0:
        matches_played = 1

    performance_score = min(
        goals * 5 + assists * 3 + saves * 3,
        40
    )
    consistency_score = min(matches_played * 2, 20)
    ability_score = (player.player_power / 100) * 30
    base_score = 40
    rating = base_score + performance_score + consistency_score + ability_score

    return round(min(rating, 100))


@login_required_custom
def update_all_ratings(request):
    """Update all player ratings - accessible to logged-in users."""
    players = Player.objects.all()

    for player in players:
        player.player_rating = calculate_player_rating(player)
        player.save()

    messages.success(request, "All player ratings updated successfully.")
    return redirect(view_players)


@club_manager_required
def club_interface(request, club_id, message=None):
    """Club dashboard - only for club managers."""
    user = user_acc(request)
    club = get_object_or_404(Club, club_id=club_id)
    request.session["current_club"] = club.club_id

    if club.club_manager != user:
        messages.error(request, "You are not authorized to view this club's dashboard.")
        return redirect("user_home")

    turfs = Turf.objects.filter(is_validated=True)
    team_players = Player.objects.filter(player_club=club)
    matches = Match.objects.filter(
        Q(match_home_team=club) | Q(match_away_team=club),
        match_date__gte=date.today()
    ).order_by("match_date")

    bookings = Booking.objects.filter(customer=user).order_by("-booking_date")
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    
    pending_bookings = Booking.objects.filter(
    customer=user,
    is_paid=False,
    status="Accepted",
    turf__is_validated=True
).select_related('turf', 'time_slot__tt_time').order_by('-booking_date')


    context = {
        "club": club,
        "turfs": turfs,
        "players": team_players,
        "matches": matches,
        "bookings": bookings,
        "is_manager": True,
        "tomorrow": tomorrow,
                
        "MIN_PLAYERS": 6,   
        "pending_bookings": pending_bookings, 
        "pending_count": pending_bookings.count(),
    }
    context.update(get_user_role_context(request))

    return render(request, "club/club_interface.html", context)

@club_manager_required
@require_POST
def remove_player_from_club(request, club_id, player_id):
    """Remove a recruited player from the club."""
    user = user_acc(request)
    club = get_object_or_404(Club, club_id=club_id)
    
    if club.club_manager != user:
        messages.error(request, "You are not authorized to manage this club's players.")
        return redirect("user_home")
    
    player = get_object_or_404(Player, player_id=player_id, player_club=club)
    
    player.player_club = None
    player.save()

    
    messages.success(request, f"{player.player_card_name} has been removed from the squad.")
    return redirect("club_interface", club_id=club.club_id)

@club_manager_required
def create_match(request):
    if request.method != 'POST':

        club_id = request.session.get(
            "current_club"
        )

        if club_id:
            return redirect(
                "club_interface",
                club_id=club_id
            )

        return redirect(
            "match_page"
        )

    home_club = get_object_or_404(
        Club,
        club_id=request.POST.get(
            'club_id'
        )
    )

    turf_id = request.POST.get(
        'turf'
    )

    match_date = request.POST.get(
        'match_date'
    )

    match_time = request.POST.get(
        'match_time'
    )

    squad_size = int(
        request.POST.get(
            'squad_size',
            5
        )
    )

    if not all([
        turf_id,
        match_date,
        match_time
    ]):

        messages.error(
            request,
            "Please select turf, date, and time slot."
        )

        return redirect(
            "match_page"
        )

    turf = get_object_or_404(
        Turf,
        turf_id=turf_id
    )


    match_time_range = str(
        match_time
    ).strip()


    if "-" in match_time_range:

        match_start_time = (
            match_time_range
            .split("-", 1)[0]
            .strip()
        )

    else:

        match_start_time = match_time_range

    slot_conflict = (

        Booking.objects.filter(

            turf=turf,

            booking_date=match_date,

            time_slot__tt_time__time_range=match_time_range,

            status__in=[
                "Pending",
                "Accepted"
            ]

        ).exists()

        or

        Match.objects.filter(

            match_turf=turf,

            match_date=match_date,

            match_time=match_start_time

        ).exists()

    )


    if slot_conflict:

        messages.error(
            request,
            "This slot is already booked. Please choose another time or turf."
        )

        return redirect(
            "club_interface",
            club_id=home_club.club_id
        )

    if turf == home_club.club_home_ground:
        match = Match.objects.create(
            match_home_team=home_club,
            match_turf=turf,
            match_date=match_date,
            # Store only HH:MM
            match_time=match_start_time,
            squad_size=squad_size,

        )

        create_notification(
            home_club.club_manager,
            (
                f"Match created! "
                f"Your team will play at "
                f"{turf.turf_name} "
                f"on {match_date} "
                f"at {match_start_time}."
            ),
            'success'
        )

        player_count = Player.objects.filter(
            player_club=home_club
        ).count()

        if player_count > squad_size:

            return redirect(
                "select_squad",
                match_id=match.match_id,
                side="home"
            )

        else:

            all_players = Player.objects.filter(
                player_club=home_club
            )

            match.home_squad.set(
                all_players[:squad_size]
            )

            match.home_subs.set(
                all_players[squad_size:]
            )

            match.home_squad_selected = True
            match.save()

            messages.success(
                request,
                (
                    f"Match created with "
                    f"{squad_size}-a-side. "
                    f"All players auto-assigned."
                )
            )

            return redirect(
                "club_interface",
                club_id=home_club.club_id
            )

    try:

        time_slot = Turf_time_map.objects.get(
            tt_turf=turf,
            tt_time__time_range=match_time_range
        )

    except Turf_time_map.DoesNotExist:
        available = list(
            Turf_time_map.objects.filter(
                tt_turf=turf
            ).values_list(
                'tt_time__time_range',
                flat=True
            )
        )


        messages.error(
            request,
            (
                f"Slot '{match_time_range}' "
                f"not found for {turf.turf_name}. "
                f"Available slots: "
                f"{', '.join(available[:5])}..."
            )
        )

        return redirect(
            "match_page"
        )

    customer = get_object_or_404(User,user_id=request.session["user_id"])

    booking = Booking.objects.create(
        customer=customer,
        turf=turf,
        club=home_club,
        booking_date=match_date,
        time_slot=time_slot,
        status="Pending",
        is_paid=False
    )

    request.session[
        'pending_squad_size'
    ] = squad_size

    return redirect(
        "initiate_payment",
        booking_id=booking.booking_id
    )

@club_manager_required
def check_match_requirement(request, club_id):
    """Check match requirements - only for club managers."""
    club = get_object_or_404(Club, club_id=club_id)
    players_count = Player.objects.filter(player_club=club).count()

    if players_count < 6:
        messages.error(
            request,
            f"Cannot create match: '{club.club_name}' has only {players_count} player(s). "
            f"Minimum required is 6."
        )
        return redirect("club_interface", club_id=club_id)

    return redirect("match_page")


@club_manager_required
def match_page(request):
    """Match page - only for club managers."""
    user = user_acc(request)
    club = get_object_or_404(Club, club_manager=user, is_validated=True)

    turfs = Turf.objects.filter(is_validated=True)
    clubs = Club.objects.filter(club_manager=user, is_validated=True)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    context = {
        "club": club,
        "turfs": turfs,
        "tomorrow": tomorrow,
        "clubs": clubs,
    }
    context.update(get_user_role_context(request))

    return render(request, "user/match_page.html", context)


@club_manager_required
def get_available_slots(request):
    """Get available slots via AJAX."""
    if request.method != "POST":
        return JsonResponse({"slots": []})

    turf_id = request.POST.get("turf_id")
    match_date = request.POST.get("match_date")
    print(f"DEBUG: turf_id={turf_id}, date={match_date}")

    if not turf_id or not match_date:
        return JsonResponse({"slots": [], "error": "Missing parameters"})

    turf = get_object_or_404(Turf, turf_id=turf_id)
    all_slots = list(Turf_time_map.objects.filter(tt_turf=turf).values_list('tt_time__time_range', flat=True))
    print(f"DEBUG: all slots for {turf.turf_name}: {all_slots}")

    booked = Booking.objects.filter(
        turf=turf, booking_date=match_date, status__in=["Pending", "Accepted"]
    ).values_list("time_slot__tt_time__time_range", flat=True)

    matched = Match.objects.filter(
        match_turf=turf, match_date=match_date
    ).values_list("match_time", flat=True)

    blocked = set(booked) | set(matched)
    available = [s for s in all_slots if s not in blocked]
    print(f"DEBUG: available: {available}")

    return JsonResponse({"slots": available})


@club_manager_required
def search_matches(request):
    """Search available matches - only for club managers."""
    current_user = user_acc(request)
    
    current_club = Club.objects.filter(club_manager=current_user, is_validated=True).first()
    if not current_club:
        messages.warning(request, "You need a validated club to browse matches.")
        return redirect("user_home")

    today = date.today()

    total_matches = Match.objects.count()
    all_future = Match.objects.filter(match_date__gte=today).count()
    open_calls_qs = Match.objects.filter(match_away_team__isnull=True, match_date__gte=today)
    open_calls_count = open_calls_qs.count()
    
    print("\n" + "="*60)
    print(f"DEBUG search_matches | User: {current_user.user_name}")
    print(f"DEBUG search_matches | Club: {current_club.club_name} (ID:{current_club.club_id})")
    print(f"DEBUG search_matches | Total Match rows in DB: {total_matches}")
    print(f"DEBUG search_matches | Future matches: {all_future}")
    print(f"DEBUG search_matches | Open calls (no away team): {open_calls_count}")
    print("="*60 + "\n")

    match_calls = open_calls_qs.exclude(
        match_home_team=current_club
    ).select_related('match_home_team', 'match_turf').order_by('match_date', 'match_time')

    upcoming_matches = Match.objects.filter(
        match_away_team__isnull=False,
        match_date__gte=today,
        match_finished=False,
    ).exclude(
        Q(match_home_team=current_club) | Q(match_away_team=current_club)
    ).select_related('match_home_team', 'match_away_team', 'match_turf').order_by('match_date', 'match_time')[:12]

   
    all_future_matches = Match.objects.filter(
        match_date__gte=today,
        match_finished=False,
    ).select_related('match_home_team', 'match_away_team', 'match_turf').order_by('match_date', 'match_time')[:12]

    for match in match_calls:
        Notification.objects.get_or_create(
            user=current_user,
            message=f"⚽ Match call available: {match.match_home_team.club_name} is waiting for an opponent on {match.match_date} ({match.match_time}).",
            defaults={'notification_type': 'info'}
        )

    context = {
        "match_calls": match_calls,
        "upcoming_matches": upcoming_matches,
        "all_future_matches": all_future_matches,   
        "open_calls_count": match_calls.count(),
        "current_club": current_club,
    }
    context.update(get_user_role_context(request))
    return render(request, "club/search_matches.html", context)


@club_manager_required
def club_matches(request):
    """Club matches — now includes PENDING BOOKINGS awaiting payment."""
    user = user_acc(request)
    clubs = Club.objects.filter(club_manager=user, is_validated=True)
    club = clubs.first()
    if club is None:
        return redirect(watch_matches)

    current_time = now()

    # ── NOT STARTED YET ──
    upcoming_matches = Match.objects.filter(
        Q(match_home_team=club) | Q(match_away_team=club),
        match_started=False,
        match_finished=False,
    ).order_by('match_date')

    upcoming_matches = upcoming_matches.annotate(
        home_count=Count('home_squad'),
        away_count=Count('away_squad')
    )

    # ── LIVE / IN PROGRESS ──
    live_matches = Match.objects.filter(
        Q(match_home_team=club) | Q(match_away_team=club),
        match_started=True,
        match_finished=False,
    ).order_by('-match_date')

    # ── COMPLETED ──
    finished_matches = Match.objects.filter(
        Q(match_home_team=club) | Q(match_away_team=club),
        match_finished=True,
    ).order_by('-match_date')

    
    pending_bookings = Booking.objects.filter(
        customer=user,
        is_paid=False,
        status__in=["Pending", "Accepted"],
        turf__is_validated=True
    ).select_related('turf', 'time_slot__tt_time').order_by('-booking_date')

    context = {
        'upcoming_matches': upcoming_matches,
        'live_matches': live_matches,
        'finished_matches': finished_matches,
        'now': current_time,
        "cur_club": club,
        "clubs": clubs,
        "pending_bookings": pending_bookings,
        "pending_count": pending_bookings.count(),
    }
    context.update(get_user_role_context(request))

    return render(request, "club/club_matches.html", context)


@club_manager_required
def cancel_match(request, match_id):
    """Cancel match - only for club managers."""
    match = Match.objects.get(match_id=match_id)

    for player in match.home_squad.all():
        create_notification(
            player.player_user,
            f"Match on {match.match_date} at {match.match_time} has been cancelled.",
            'error'
        )
    if match.match_away_team:
        for player in match.away_squad.all():
            create_notification(
                player.player_user,
                f"Match on {match.match_date} at {match.match_time} has been cancelled.",
                'error'
            )

    match.delete()
    messages.success(request, "Match cancelled successfully.")

    return redirect("club_matches")


@club_manager_required
def fix_match(request, match_id):
    """Fix match (join as away team) - only for club managers."""
    current_user = user_acc(request)
    current_club = get_object_or_404(Club, club_manager=current_user, is_validated=True)

    match = Match.objects.get(match_id=match_id)
    match.match_away_team = current_club
    match.save()

    create_notification(
        match.match_home_team.club_manager,
        f"{current_club.club_name} has accepted your match call! Match on {match.match_date} at {match.match_time} is confirmed.",
        'success'
    )

    player_count = Player.objects.filter(player_club=current_club).count()
    squad_size = match.squad_size

    if player_count > squad_size:
        return redirect("select_squad", match_id=match.match_id, side="away")
    else:
        all_players = Player.objects.filter(player_club=current_club)
        match.away_squad.set(all_players[:squad_size])
        match.away_subs.set(all_players[squad_size:])
        match.away_squad_selected = True
        match.save()
        messages.success(request, f"Away team joined and all players auto-assigned ({squad_size}-a-side).")

        for player in match.away_squad.all():
            create_notification(
                player.player_user,
                f"You have been auto-assigned to the away team match on {match.match_date} at {match.match_time}.",
                'info'
            )

        return redirect("club_matches")


@login_required_custom
def start_match(request, match_id):
    """
    Start a match only after BOTH teams have completed squad selection.

    Tournament matches:
        - Both home and away teams must select their squads first.
        - Only the tournament host can start the match.

    Friendly matches:
        - Both home and away teams must select their squads first.
        - Only the home-team manager can start the match.
    """
    match = get_object_or_404(Match, match_id=match_id)
    user = user_acc(request)

    if request.method not in ("GET", "POST"):
        return redirect("go_to_match", match_id=match_id)

    if match.match_started:
        messages.warning(request, "Match has already started.")
        return redirect("go_to_match", match_id=match_id)

    if match.match_finished:
        messages.error(request, "This match has already finished.")
        return redirect("go_to_match", match_id=match_id)

    # Both teams are required before a match can start.
    if not match.match_home_team or not match.match_away_team:
        messages.error(
            request,
            "Both teams must be confirmed before the match can start."
        )
        if match.tournament:
            return redirect("view_tournament", t_id=match.tournament.t_id)
        return redirect("club_matches")

    # ---------------------------------------------------------
    # STRICT SQUAD REQUIREMENT
    # ---------------------------------------------------------
    if not match.home_squad_selected:
        messages.error(
            request,
            "Home team must select its squad before the match can start."
        )
        if match.tournament:
            return redirect("view_tournament", t_id=match.tournament.t_id)
        return redirect("go_to_match", match_id=match_id)

    if not match.away_squad_selected:
        messages.error(
            request,
            "Away team must select its squad before the match can start."
        )
        if match.tournament:
            return redirect("view_tournament", t_id=match.tournament.t_id)
        return redirect("go_to_match", match_id=match_id)

    # Also verify that selected starters actually exist.
    if match.home_squad.count() == 0:
        messages.error(
            request,
            "Home squad is marked ready but contains no selected players."
        )
        if match.tournament:
            return redirect("view_tournament", t_id=match.tournament.t_id)
        return redirect("go_to_match", match_id=match_id)

    if match.away_squad.count() == 0:
        messages.error(
            request,
            "Away squad is marked ready but contains no selected players."
        )
        if match.tournament:
            return redirect("view_tournament", t_id=match.tournament.t_id)
        return redirect("go_to_match", match_id=match_id)

    # ---------------------------------------------------------
    # START PERMISSION
    # ---------------------------------------------------------
    if match.tournament:
        if (
            not match.tournament.t_host
            or match.tournament.t_host.club_manager != user
        ):
            messages.error(
                request,
                "Only the tournament host can start tournament matches."
            )
            return redirect(
                "view_tournament",
                t_id=match.tournament.t_id
            )
    else:
        if (
            not match.match_home_team
            or match.match_home_team.club_manager != user
        ):
            messages.error(
                request,
                "Only the home team manager can start this match."
            )
            return redirect("club_matches")

    # ---------------------------------------------------------
    # START MATCH
    # ---------------------------------------------------------
    match.match_started = True
    match.match_finished = False
    match.match_started_at = timezone.now()
    match.match_elapsed_seconds = 0
    match.match_paused = False
    match.match_paused_at = None
    match.match_finished_at = None
    match.save()

    for player in match.home_squad.all():
        create_notification(
            player.player_user,
            "The match has started! Good luck! ⚽",
            "success"
        )

    for player in match.away_squad.all():
        create_notification(
            player.player_user,
            "The match has started! Good luck! ⚽",
            "success"
        )

    messages.success(request, "Match started successfully!")
    return redirect("go_to_match", match_id=match_id)


@login_required_custom
def pause_match(request, match_id):
    """Pause a live match - home manager for friendlies, tournament host for tournaments."""
    match = get_object_or_404(Match, match_id=match_id)
    user = user_acc(request)

    if request.method != "POST":
        return redirect("go_to_match", match_id=match_id)

    if match.match_finished:
        messages.error(request, "Cannot pause a finished match.")
        return redirect("go_to_match", match_id=match_id)

    if not match.match_started:
        messages.error(request, "Match has not started yet.")
        return redirect("go_to_match", match_id=match_id)

    if match.match_paused:
        messages.warning(request, "Match is already paused.")
        return redirect("go_to_match", match_id=match_id)

    if match.tournament:
        if not match.tournament.t_host or match.tournament.t_host.club_manager != user:
            messages.error(request, "Only the tournament host can pause this match.")
            return redirect("view_tournament", t_id=match.tournament.t_id)
    else:
        if not match.match_home_team or match.match_home_team.club_manager != user:
            messages.error(request, "Only the home team manager can pause this match.")
            return redirect("club_matches")

    current_time = timezone.now()

    if match.match_started_at:
        elapsed = int(
            (current_time - match.match_started_at).total_seconds()
        )
        match.match_elapsed_seconds += max(0, elapsed)

    match.match_paused = True
    match.match_paused_at = current_time
    match.match_started_at = None
    match.save()

    messages.info(request, "Match paused.")
    return redirect("go_to_match", match_id=match_id)

@login_required_custom
def resume_match(request, match_id):
    """Resume a paused match - home manager for friendlies, tournament host for tournaments."""
    match = get_object_or_404(Match, match_id=match_id)
    user = user_acc(request)

    if request.method != "POST":
        return redirect("go_to_match", match_id=match_id)

    if match.match_finished:
        messages.error(request, "Cannot resume a finished match.")
        return redirect("go_to_match", match_id=match_id)

    if not match.match_started:
        messages.error(request, "Match has not started yet.")
        return redirect("go_to_match", match_id=match_id)

    if not match.match_paused:
        messages.warning(request, "Match is already running.")
        return redirect("go_to_match", match_id=match_id)

    if match.tournament:
        if not match.tournament.t_host or match.tournament.t_host.club_manager != user:
            messages.error(request, "Only the tournament host can resume this match.")
            return redirect("view_tournament", t_id=match.tournament.t_id)
    else:
        if not match.match_home_team or match.match_home_team.club_manager != user:
            messages.error(request, "Only the home team manager can resume this match.")
            return redirect("club_matches")

    match.match_started_at = timezone.now()
    match.match_paused = False
    match.match_paused_at = None
    match.save()

    messages.success(request, "Match resumed.")
    return redirect("go_to_match", match_id=match_id)
    
@login_required_custom
def finish_match(request, match_id):

    match = get_object_or_404(
        Match,
        match_id=match_id
    )

    user = user_acc(request)

    if match.tournament:

        if match.tournament.t_host.club_manager != user:

            messages.error(
                request,
                "Only the tournament host can finish this match."
            )

            return redirect(
                "view_tournament",
                t_id=match.tournament.t_id
            )

    else:

        if (
            not match.match_home_team
            or match.match_home_team.club_manager != user
        ):

            messages.error(
                request,
                "Only the home team manager can finish this match."
            )

            return redirect(
                "club_matches"
            )

    if match.match_finished:

        messages.info(
            request,
            "This match is already finished."
        )

        return redirect(
            "go_to_match",
            match_id=match_id
        )

    if not match.match_started:

        messages.warning(
            request,
            "The match has not started."
        )

        return redirect(
            "go_to_match",
            match_id=match_id
        )

    now = timezone.now()

    if (
        match.match_started_at
        and not match.match_paused
    ):

        elapsed = (
            now - match.match_started_at
        ).total_seconds()

        match.match_elapsed_seconds += int(
            max(0, elapsed)
        )

    match.match_finished = True
    match.match_finished_at = now

    match.match_started = False
    match.match_paused = False

    match.match_started_at = None
    match.match_paused_at = None

    match.save(
        update_fields=[
            "match_elapsed_seconds",
            "match_finished",
            "match_finished_at",
            "match_started",
            "match_paused",
            "match_started_at",
            "match_paused_at",
        ]
    )

    for player in match.home_squad.all():

        create_notification(
            player.player_user,
            "The match has finished! ⚽",
            "success"
        )

    for player in match.away_squad.all():

        create_notification(
            player.player_user,
            "The match has finished! ⚽",
            "success"
        )

    messages.success(
        request,
        "Match finished successfully!"
    )

    return redirect(
        "go_to_match",
        match_id=match_id
    )


@login_required_custom
def watch_live_score(request, match_id):
    """
    Watch live/final match score.

    Event minutes are calculated from the match timer and the event's
    recorded time. This works for running, paused and finished matches.
    """

    match = get_object_or_404(
        Match.objects
        .select_related(
            "match_home_team",
            "match_away_team",
            "match_turf",
            "tournament",
        )
        .prefetch_related(
            "home_squad",
            "away_squad",
        ),
        match_id=match_id,
    )

    # Both teams are required.
    if (
        not match.match_home_team
        or not match.match_away_team
    ):
        return redirect("watch_matches")

    # ---------------------------------------------------------
    # RESULT
    # ---------------------------------------------------------

    result = (
        Result.objects
        .filter(
            result_match=match
        )
        .first()
    )

    # ---------------------------------------------------------
    # MATCH EVENTS
    # ---------------------------------------------------------

    if result:

        goals = list(
            Goal.objects
            .filter(result=result)
            .select_related(
                "player",
                "for_club",
            )
        )

        assists = list(
            Assist.objects
            .filter(result=result)
            .select_related(
                "player",
                "for_club",
            )
        )

        saves = list(
            Save.objects
            .filter(result=result)
            .select_related(
                "player",
                "for_club",
            )
        )

    else:

        goals = []
        assists = []
        saves = []

    # ---------------------------------------------------------
    # SET EVENT TYPES
    # ---------------------------------------------------------

    for goal in goals:
        goal.achievement_type = "goal"

    for assist in assists:
        assist.achievement_type = "assist"

    for save in saves:
        save.achievement_type = "save"

    # ---------------------------------------------------------
    # MATCH TIMER
    # ---------------------------------------------------------

    stored_elapsed = (
        match.match_elapsed_seconds or 0
    )

    stored_elapsed = max(
        0,
        int(stored_elapsed)
    )

    match_duration = (
        match.match_duration or 5400
    )

    match_duration = max(
        1,
        int(match_duration)
    )

    match_elapsed = stored_elapsed

    # ---------------------------------------------------------
    # CURRENT RUNNING PERIOD
    # ---------------------------------------------------------

    if (
        match.match_started
        and not match.match_paused
        and not match.match_finished
        and match.match_started_at
    ):

        running_seconds = int(
            (
                timezone.now()
                - match.match_started_at
            ).total_seconds()
        )

        running_seconds = max(
            0,
            running_seconds
        )

        match_elapsed = (
            stored_elapsed
            + running_seconds
        )

    # Never exceed match duration.
    match_elapsed = min(
        match_elapsed,
        match_duration
    )

    # ---------------------------------------------------------
    # COMBINE EVENTS
    # ---------------------------------------------------------

    all_events = (
        goals
        + assists
        + saves
    )

    # ---------------------------------------------------------
    # CALCULATE EVENT MINUTES
    # ---------------------------------------------------------

    for achievement in all_events:

        event_time = getattr(
            achievement,
            "time",
            None
        )

        event_minute = None

        # -----------------------------------------------------
        # CASE 1: EVENT HAS A RECORDED TIME
        # -----------------------------------------------------

        if event_time:

            # If the match started at this point, calculate
            # the actual match minute from kickoff.
            if match.match_started_at:

                elapsed_at_event = (
                    event_time
                    - match.match_started_at
                ).total_seconds()

                event_minute = int(
                    elapsed_at_event // 60
                ) + 1

            # If the match has already been finished and
            # match_started_at has been cleared, fall back
            # to the stored elapsed time only when necessary.
            elif match.match_finished:

                event_minute = int(
                    stored_elapsed // 60
                ) + 1

        # -----------------------------------------------------
        # CASE 2: PAUSED MATCH
        # -----------------------------------------------------

        if (
            event_minute is None
            and match.match_paused
        ):

            event_minute = int(
                stored_elapsed // 60
            ) + 1

        # -----------------------------------------------------
        # CASE 3: NO EVENT TIME
        # -----------------------------------------------------

        if event_minute is None:

            event_minute = 1

        # -----------------------------------------------------
        # LIMIT TO NORMAL FOOTBALL RANGE
        # -----------------------------------------------------

        event_minute = max(
            1,
            min(
                event_minute,
                120
            )
        )

        # Attach the value for template display.
        achievement.match_minute = event_minute

    # ---------------------------------------------------------
    # SORT EVENTS
    # ---------------------------------------------------------

    def event_sort_key(event):

        event_time = getattr(
            event,
            "time",
            None
        )

        if event_time is None:
            return timezone.make_aware(
                datetime.min
            )

        return event_time

    achievements = sorted(
        all_events,
        key=event_sort_key,
        reverse=True
    )

    # ---------------------------------------------------------
    # TIMER STATUS
    # ---------------------------------------------------------

    if match.match_finished:

        timer_status = "finished"

    elif match.match_paused:

        timer_status = "paused"

    elif match.match_started:

        timer_status = "running"

    else:

        timer_status = "not_started"

    # ---------------------------------------------------------
    # MATCH FLAGS
    # ---------------------------------------------------------

    match_is_live = (
        match.match_started
        and not match.match_finished
    )

    match_is_paused = bool(
        match.match_paused
    )

    match_is_finished = bool(
        match.match_finished
    )

    # ---------------------------------------------------------
    # CONTEXT
    # ---------------------------------------------------------

    context = {

        "match": match,

        "result": result,

        "achievements": achievements,

        "match_elapsed_seconds": match_elapsed,

        "match_duration": match_duration,

        "match_started": match.match_started,

        "match_started_at": match.match_started_at,

        "match_paused": match.match_paused,

        "match_paused_at": match.match_paused_at,

        "match_finished": match.match_finished,

        "match_finished_at": match.match_finished_at,

        "timer_status": timer_status,

        "match_is_live": match_is_live,

        "match_is_paused": match_is_paused,

        "match_is_finished": match_is_finished,
    }

    # Global header / role context.
    context.update(
        get_user_role_context(request)
    )

    return render(
        request,
        "user/watch_live_score.html",
        context,
    )


# ============================================================
# HOME TEAM SCORE / ACTION RECORDER
# ============================================================

@match_manager_required
def home_score_recorder(request, match_id):
    """
    Record home-team goal, assist or save.

    Tournament matches are handled by the tournament host.
    """

    if request.method != "POST":

        return redirect(
            "club_matches"
        )

    # ---------------------------------------------------------
    # MATCH
    # ---------------------------------------------------------

    match = get_object_or_404(
        Match,
        match_id=match_id
    )

    # ---------------------------------------------------------
    # TOURNAMENT MATCH
    # ---------------------------------------------------------

    if match.tournament:

        messages.error(
            request,
            "Tournament match scores are managed by the tournament host. "
            "Use the bracket page to update scores."
        )

        return redirect(
            "tournament_bracket",
            t_id=match.tournament.t_id
        )

    # ---------------------------------------------------------
    # FORM DATA
    # ---------------------------------------------------------

    action = request.POST.get(
        "action"
    )

    player_id = request.POST.get(
        "home_player"
    )

    if (
        not player_id
        or not action
    ):

        messages.error(
            request,
            "Missing required match data."
        )

        return redirect(
            "club_matches"
        )

    # ---------------------------------------------------------
    # PLAYER
    # ---------------------------------------------------------

    player = get_object_or_404(
        Player,
        player_id=player_id
    )

    # ---------------------------------------------------------
    # RESULT
    # ---------------------------------------------------------

    result = get_object_or_404(
        Result,
        result_match=match
    )

    # ---------------------------------------------------------
    # VALIDATE PLAYER TEAM
    # ---------------------------------------------------------

    home_club = match.match_home_team

    if player.player_club != home_club:

        messages.error(
            request,
            "Selected player does not belong to the home team."
        )

        return redirect(
            "go_to_match",
            match_id=match_id
        )

    # ---------------------------------------------------------
    # MATCH MUST BE LIVE
    # ---------------------------------------------------------

    if (
        not match.match_started
        or match.match_finished
    ):

        messages.error(
            request,
            "The match must be live before recording an action."
        )

        return redirect(
            "go_to_match",
            match_id=match_id
        )

    # ---------------------------------------------------------
    # CALCULATE CURRENT MATCH MINUTE
    # ---------------------------------------------------------

    now = timezone.now()

    stored_elapsed = (
        match.match_elapsed_seconds or 0
    )

    stored_elapsed = max(
        0,
        int(stored_elapsed)
    )

    current_elapsed = stored_elapsed

    # Match currently running.
    if (
        not match.match_paused
        and match.match_started_at
    ):

        running_seconds = int(
            (
                now
                - match.match_started_at
            ).total_seconds()
        )

        running_seconds = max(
            0,
            running_seconds
        )

        current_elapsed = (
            stored_elapsed
            + running_seconds
        )

    # If paused, stored_elapsed is already the correct
    # elapsed match time.
    current_elapsed = min(
        current_elapsed,
        match.match_duration or 5400
    )

    match_minute = max(
        1,
        min(
            int(current_elapsed // 60) + 1,
            120
        )
    )

    # ---------------------------------------------------------
    # CREATE ACTION
    # ---------------------------------------------------------

    if action == "goal":

        table = Goal()

        result.result_home_team += 1

        notif_msg = (
            f"GOAL! "
            f"{player.player_card_name} "
            f"scored for "
            f"{home_club.club_name}!"
        )

        notif_type = "success"

    elif action == "assist":

        table = Assist()

        notif_msg = (
            f"ASSIST! "
            f"{player.player_card_name} "
            f"provided an assist for "
            f"{home_club.club_name}!"
        )

        notif_type = "info"

    elif action == "save":

        table = Save()

        notif_msg = (
            f"SAVE! "
            f"{player.player_card_name} "
            f"made a crucial save for "
            f"{home_club.club_name}!"
        )

        notif_type = "info"

    else:

        messages.warning(
            request,
            "Invalid action selected."
        )

        return redirect(
            "go_to_match",
            match_id=match_id
        )

    # ---------------------------------------------------------
    # SAVE ACTION
    # ---------------------------------------------------------

    table.player = player

    table.result = result

    table.for_club = home_club

    # Store the current match minute on the object.
    # watch_live_score will also calculate it again when
    # displaying the event.
    table.match_minute = match_minute

    table.save()

    # Save updated score.
    result.save()

    # ---------------------------------------------------------
    # UPDATE PLAYER RATING
    # ---------------------------------------------------------

    player.player_rating = calculate_player_rating(
        player
    )

    player.save()

    # ---------------------------------------------------------
    # NOTIFY HOME TEAM
    # ---------------------------------------------------------

    for p in match.home_squad.all():

        create_notification(
            p.player_user,
            notif_msg,
            notif_type
        )

    # ---------------------------------------------------------
    # NOTIFY AWAY TEAM
    # ---------------------------------------------------------

    for p in match.away_squad.all():

        create_notification(
            p.player_user,
            notif_msg,
            notif_type
        )

    messages.success(
        request,
        notif_msg
    )

    return redirect(
        "go_to_match",
        match_id=match_id
    )


# ============================================================
# AWAY TEAM SCORE / ACTION RECORDER
# ============================================================

@match_away_manager_required
def away_score_recorder(request, match_id):
    """
    Record away-team goal, assist or save.

    Tournament matches are handled by the tournament host.
    """

    if request.method != "POST":

        return redirect(
            "club_matches"
        )

    # ---------------------------------------------------------
    # MATCH
    # ---------------------------------------------------------

    match = get_object_or_404(
        Match,
        match_id=match_id
    )

    # ---------------------------------------------------------
    # TOURNAMENT MATCH
    # ---------------------------------------------------------

    if match.tournament:

        messages.error(
            request,
            "Tournament match scores are managed by the tournament host. "
            "Use the bracket page to update scores."
        )

        return redirect(
            "tournament_bracket",
            t_id=match.tournament.t_id
        )

    # ---------------------------------------------------------
    # FORM DATA
    # ---------------------------------------------------------

    action = request.POST.get(
        "action"
    )

    player_id = request.POST.get(
        "away_player"
    )

    if (
        not player_id
        or not action
    ):

        messages.error(
            request,
            "Missing required match data."
        )

        return redirect(
            "club_matches"
        )

    # ---------------------------------------------------------
    # PLAYER
    # ---------------------------------------------------------

    player = get_object_or_404(
        Player,
        player_id=player_id
    )

    # ---------------------------------------------------------
    # RESULT
    # ---------------------------------------------------------

    result = get_object_or_404(
        Result,
        result_match=match
    )

    # ---------------------------------------------------------
    # VALIDATE PLAYER TEAM
    # ---------------------------------------------------------

    away_club = match.match_away_team

    if player.player_club != away_club:

        messages.error(
            request,
            "Selected player does not belong to the away team."
        )

        return redirect(
            "go_to_match",
            match_id=match_id
        )

    # ---------------------------------------------------------
    # MATCH MUST BE LIVE
    # ---------------------------------------------------------

    if (
        not match.match_started
        or match.match_finished
    ):

        messages.error(
            request,
            "The match must be live before recording an action."
        )

        return redirect(
            "go_to_match",
            match_id=match_id
        )

    # ---------------------------------------------------------
    # CALCULATE CURRENT MATCH MINUTE
    # ---------------------------------------------------------

    now = timezone.now()

    stored_elapsed = (
        match.match_elapsed_seconds or 0
    )

    stored_elapsed = max(
        0,
        int(stored_elapsed)
    )

    current_elapsed = stored_elapsed

    # Match currently running.
    if (
        not match.match_paused
        and match.match_started_at
    ):

        running_seconds = int(
            (
                now
                - match.match_started_at
            ).total_seconds()
        )

        running_seconds = max(
            0,
            running_seconds
        )

        current_elapsed = (
            stored_elapsed
            + running_seconds
        )

    current_elapsed = min(
        current_elapsed,
        match.match_duration or 5400
    )

    match_minute = max(
        1,
        min(
            int(current_elapsed // 60) + 1,
            120
        )
    )

    # ---------------------------------------------------------
    # CREATE ACTION
    # ---------------------------------------------------------

    if action == "goal":

        table = Goal()

        result.result_away_team += 1

        notif_msg = (
            f"GOAL! "
            f"{player.player_card_name} "
            f"scored for "
            f"{away_club.club_name}!"
        )

        notif_type = "success"

    elif action == "assist":

        table = Assist()

        notif_msg = (
            f"ASSIST! "
            f"{player.player_card_name} "
            f"provided an assist for "
            f"{away_club.club_name}!"
        )

        notif_type = "info"

    elif action == "save":

        table = Save()

        notif_msg = (
            f"SAVE! "
            f"{player.player_card_name} "
            f"made a crucial save for "
            f"{away_club.club_name}!"
        )

        notif_type = "info"

    else:

        messages.warning(
            request,
            "Invalid action selected."
        )

        return redirect(
            "go_to_match",
            match_id=match_id
        )

    # ---------------------------------------------------------
    # SAVE ACTION
    # ---------------------------------------------------------

    table.player = player

    table.result = result

    table.for_club = away_club

    # Store current match minute.
    table.match_minute = match_minute

    table.save()

    # Save updated score.
    result.save()

    # ---------------------------------------------------------
    # UPDATE PLAYER RATING
    # ---------------------------------------------------------

    player.player_rating = calculate_player_rating(
        player
    )

    player.save()

    # ---------------------------------------------------------
    # NOTIFY HOME TEAM
    # ---------------------------------------------------------

    for p in match.home_squad.all():

        create_notification(
            p.player_user,
            notif_msg,
            notif_type
        )

    # ---------------------------------------------------------
    # NOTIFY AWAY TEAM
    # ---------------------------------------------------------

    for p in match.away_squad.all():

        create_notification(
            p.player_user,
            notif_msg,
            notif_type
        )

    messages.success(
        request,
        notif_msg
    )

    return redirect(
        "go_to_match",
        match_id=match_id
    )

@club_manager_required
def match_result(request, match_id):
    """View match result - only for club managers."""
    match = Match.objects.get(match_id=match_id)
    home_team = match.match_home_team
    away_team = match.match_away_team
    result = Result.objects.get(result_match=match_id)

    is_manager = home_team.club_manager == user_acc(request)

    home_goal_counts = (
        Goal.objects.filter(result=result, for_club=home_team)
        .values('player__player_card_name', 'player__player_id')
        .annotate(goal_count=Count('goal_id')).order_by('-goal_count')
    )

    away_goal_counts = (
        Goal.objects.filter(result=result, for_club=away_team)
        .values('player__player_card_name', 'player__player_id')
        .annotate(goal_count=Count('goal_id')).order_by('-goal_count')
    )

    context = {
        "result": result,
        "home_goal_counts": home_goal_counts,
        "away_goal_counts": away_goal_counts,
        "is_manager": is_manager
    }
    context.update(get_user_role_context(request))

    return render(request, "club/match_result.html", context)


@club_manager_required
def upload_video(request, re_id):
    """Upload match video - only for club managers."""
    result = Result.objects.get(result_id=re_id)
    match = result.result_match

    if request.method == "POST":
        result_video = request.FILES.get("match_video")
        if result_video:
            result.result_video = result_video
            result.save()

            for player in match.home_squad.all():
                create_notification(
                    player.player_user,
                    "Match video has been uploaded! Watch the highlights now.",
                    'success'
                )
            for player in match.away_squad.all():
                create_notification(
                    player.player_user,
                    "Match video has been uploaded! Watch the highlights now.",
                    'success'
                )

    return redirect("match_result", match.match_id)


@club_manager_required
def recruit_player(request, club_id, player_id):
    """Recruit player - only for club managers."""
    club = get_object_or_404(Club, club_id=club_id, is_validated=True)
    player = get_object_or_404(Player, player_id=player_id)

    if player.player_club:
        messages.error(request, "Player is already in a club.")
    else:
        player.player_club = club
        player.save()

        messages.success(request, f"{player.player_card_name} recruited to {club.club_name}.")

        create_notification(
            player.player_user,
            f"🎉 Congratulations! You have been recruited to {club.club_name}!",
            'success'
        )

        create_notification(
            club.club_manager,
            f"{player.player_card_name} has joined your club {club.club_name}.",
            'success'
        )

    return redirect("club_interface", club_id=club_id)


@club_manager_required
def remove_player(request, player_id):
    """Remove player from club - only for club managers."""
    if not request.session.get("user_id"):
        return redirect("user_login")

    club_id = request.session.get("current_club")
    club = get_object_or_404(Club, club_id=club_id)
    player = get_object_or_404(Player, player_id=player_id)

    player.player_club = None
    player.save()

    messages.success(request, f"{player.player_card_name} has been removed from {club.club_name}.")

    create_notification(
        player.player_user,
        f"You have been removed from {club.club_name}.",
        'error'
    )

    return redirect("club_interface", club_id=club_id)


@club_manager_required
def my_clubs(request):
    """My clubs list - only for club managers."""
    clubs = Club.objects.filter(club_manager=user_acc(request))

    context = {
        "clubs": clubs,
        "is_manager": check_manager(request)
    }
    context.update(get_user_role_context(request))

    return render(request, "user/my_clubs_list.html", context)


@login_required_custom
def register_club(request):
    """Register club - any logged-in user can create their first club."""
    user = user_acc(request)
    if Club.objects.filter(club_manager=user).exists():
        messages.warning(request, "You have already registered a club. Please wait for admin validation or manage your existing club.")
        return redirect("my_clubs")

    
    if Turf.objects.filter(turf_owner=user).exists():
        messages.error(request, "Turf owners cannot register clubs due to conflict of interest.")
        return redirect("user_home")

    
    table = Club()
    turfs = Turf.objects.filter(is_validated=True)

    if request.method == "POST":
        table.club_manager = user
        table.club_name = request.POST.get("club_name")
        table.club_district = request.POST.get("club_district")
        table.club_location = request.POST.get("club_location")
        table.club_home_ground = get_object_or_404(Turf, turf_id=request.POST.get("home_ground"), is_validated=True)
        table.club_logo = request.FILES["club_logo"]
        table.save()

        create_notification(
            user,
            f"Club '{table.club_name}' registered successfully! Awaiting admin validation.",
            'success'
        )

        return redirect("user_clubs")

    context = {"turfs": turfs}
    context.update(get_user_role_context(request))

    return render(request, "user/register_club.html", context)



@club_manager_required
def club_update(request, club_id):
    """Update club - only for club managers."""
    club = get_object_or_404(Club, club_id=club_id, is_validated=True)
    turf = Turf.objects.filter(is_validated=True)

    if request.method == "POST":
        club.club_name = request.POST.get("club_name")
        club.club_home_ground_id = request.POST.get("club_home_ground")

        if 'club_logo' in request.FILES:
            club.club_logo = request.FILES['club_logo']

        club.save()

        create_notification(
            club.club_manager,
            f"Club '{club.club_name}' updated successfully.",
            'success'
        )

    return redirect("club_interface", club_id)


@club_manager_required
def quit_club(request):
    """Quit club - only for players who are club managers."""
    if request.method == "POST":
        user = user_acc(request)
        player = Player.objects.filter(player_user=user).first()

        if player and player.player_club:
            old_club = player.player_club
            player.player_club = None
            player.save()

            create_notification(
                user,
                f"You have left {old_club.club_name}.",
                'info'
            )

    return redirect(my_card)


@turf_owner_required
def turf_owner_home(request):
    """Turf owner unified dashboard."""
    user = user_acc(request)
    context = _get_turf_owner_context(request, user, active_tab='dashboard')
    return render(request, "turf/turf_owner_home.html", context)


@turf_owner_required
def turf_booking_requests(request):
    """Turf booking requests - renders unified dashboard on Requests tab."""
    user = user_acc(request)
    context = _get_turf_owner_context(request, user, active_tab='requests')
    return render(request, "turf/turf_owner_home.html", context)

@turf_owner_required
def approve_booking(request, booking_id):
    """Approve booking - only for turf owners."""
    booking = get_object_or_404(Booking, booking_id=booking_id)
    booking.status = "Accepted"
    booking.save()

    create_notification(
        booking.customer,
        f"✅ Your booking at {booking.turf.turf_name} on {booking.booking_date} "
        f"({booking.time_slot.tt_time.time_range}) has been approved!",
        'success'
    )
    create_notification(
        booking.turf.turf_owner,
        f"Booking approved for {booking.customer.user_name} at {booking.turf.turf_name}.",
        'success'
    )

    messages.success(request, "Booking approved successfully.")
    return redirect("turf_booking_requests")


@turf_owner_required
def reject_booking(request, booking_id):
    """Reject booking - only for turf owners."""
    booking = get_object_or_404(Booking, booking_id=booking_id)
    booking.status = "Rejected"
    booking.save()

    create_notification(
        booking.customer,
        f"❌ Your booking at {booking.turf.turf_name} on {booking.booking_date} "
        f"({booking.time_slot.tt_time.time_range}) has been rejected.",
        'error'
    )

    messages.warning(request, "Booking rejected.")
    return redirect("turf_booking_requests")


@turf_owner_required
def turf_payments(request):
    """Turf payments - renders unified dashboard on Payments tab."""
    user = user_acc(request)
    context = _get_turf_owner_context(request, user, active_tab='payments')
    return render(request, "turf/turf_owner_home.html", context)

@turf_owner_required
def accept_booking_alt(request, booking_id):
    """Accept booking (alternative) - only for turf owners."""
    booking = get_object_or_404(Booking, booking_id=booking_id)
    booking.status = "Accepted"
    booking.save()

    if booking.is_paid:
        messages.success(request, "Booking accepted and payment confirmed.")
    else:
        messages.warning(request, "Booking accepted, but payment is still pending.")

    create_notification(
        booking.customer,
        f"📅 Your booking at {booking.turf.turf_name} on {booking.booking_date} "
        f"({booking.time_slot.tt_time.time_range}) has been accepted.",
        'success'
    )

    return redirect("turf_owner_home")


@turf_owner_required
def user_turfs(request):
    """View my turfs - renders unified dashboard on My Turfs tab."""
    user = user_acc(request)
    context = _get_turf_owner_context(request, user, active_tab='myturfs')
    return render(request, "turf/turf_owner_home.html", context)


@turf_owner_required
def update_turf(request, turf_id):
    """Update turf - renders unified dashboard on Update Turf tab."""
    turf = get_object_or_404(Turf, turf_id=turf_id)
    owner = user_acc(request)

    # Security check
    if turf.turf_owner != owner:
        messages.error(request, "You are not authorized to update this turf.")
        return redirect("turf_owner_home")

    if request.method == "POST":
        turf.turf_name = request.POST.get("turf_name")
        turf.turf_district = request.POST.get("turf_district")
        turf.turf_location = request.POST.get("turf_location")
        turf.turf_rate = request.POST.get("turf_rate")

        uploaded_image = request.FILES.get("turf_image")
        if uploaded_image:
            turf.turf_image = uploaded_image

        turf.save()

        create_notification(
            owner,
            f"Turf '{turf.turf_name}' updated successfully.",
            'success'
        )
        messages.success(request, f"Turf '{turf.turf_name}' updated successfully.")

    context = _get_turf_owner_context(request, owner, active_tab='updateturf', selected_turf=turf)
    return render(request, "turf/turf_owner_home.html", context)


@login_required_custom
def register_turf(request):
    """Register turf - any logged-in user can register their first turf."""
    user = user_acc(request)
    # BLOCK: already owns ANY turf (pending or validated)
    if Turf.objects.filter(turf_owner=user).exists():
        messages.warning(request, "You have already registered a turf. Please wait for admin validation or manage your existing turf.")
        return redirect("user_turfs")
    is_player = Player.objects.filter(player_user=user).exists()
    is_manager = Club.objects.filter(club_manager=user).exists()
    if is_player or is_manager:
        messages.error(request, "Players and club managers cannot register turfs due to conflict of interest.")
        return redirect("user_home")
    
    table = Turf()

    if request.method == "POST":
        table.turf_owner = user
        table.turf_name = request.POST.get("turf_name")
        table.turf_district = request.POST.get("turf_district")
        table.turf_location = request.POST.get("turf_location")
        table.turf_rate = request.POST.get("turf_rate")
        table.turf_image = request.FILES["turf_image"]
        table.save()

        create_notification(
            user,
            f"Turf '{table.turf_name}' registered successfully! Awaiting admin validation.",
            'success'
        )

        return redirect("user_turfs")

    context = {}
    context.update(get_user_role_context(request))

    return render(request, "user/register_turf.html", context)


@turf_owner_required
def add_time_map(request, turf_id):
    """Add time slot to turf - only for turf owners."""
    if request.method == "POST":
        turf = get_object_or_404(Turf, turf_id=turf_id, is_validated=True)
        slot_id = request.POST.get("slot_id")

        if slot_id:
            time = get_object_or_404(Time_Schedule, time_id=slot_id)
            Turf_time_map.objects.get_or_create(tt_turf=turf, tt_time=time)

            create_notification(
                turf.turf_owner,
                f"Time slot {time.time_range} added to {turf.turf_name}.",
                'success'
            )
            messages.success(request, f"Time slot {time.time_range} added successfully.")

    return redirect("update_turf", turf_id=turf_id)


@turf_owner_required
def remove_time_map(request, map_id):
    """Remove time slot from turf - only for turf owners."""
    time_map = get_object_or_404(Turf_time_map, tt_id=map_id)
    turf_id = time_map.tt_turf.turf_id
    time_map.delete()
    messages.success(request, "Time slot removed successfully.")
    return redirect("update_turf", turf_id=turf_id)


@login_required_custom
def register_player_card(request):
    if request.method != "POST":
        return redirect("my_card")

    user = user_acc(request)

    if Turf.objects.filter(turf_owner=user).exists():
        messages.error(request, "Turf owners cannot register as players.")
        return redirect("user_home")

    player = Player.objects.filter(player_user=user).first()

    height = int(request.POST.get("player_height", 170))
    weight = int(request.POST.get("player_weight", 70))
    strong_foot = request.POST.get("player_foot", "Right")
    age = int(request.POST.get("user_age", user.user_age or 20))
    user.user_age = age
    user.save()

    player_power = calculate_player_power(
        user.user_gender, user.user_age, height, weight, strong_foot
    )

    card_name = request.POST.get("card_name") or user.user_name
    position = Position.objects.get(position_id=request.POST.get("player_position"))
    district = request.POST.get("player_district", "")
    location = request.POST.get("player_location", "")
    image = request.FILES.get("player_image")

    if player:
        # UPDATE
        player.player_card_name = card_name
        player.player_position = position
        player.player_strong_foot = strong_foot
        player.player_height = height
        player.player_weight = weight
        player.player_power = player_power
        player.player_district = district
        player.player_location = location
        if image:
            player.player_image = image
        player.save()
        redirect_id = player.player_id
        messages.success(request, "Profile updated successfully!")
    else:
        # CREATE
        new_player = Player.objects.create(
            player_user=user, player_card_name=card_name,
            player_position=position, player_strong_foot=strong_foot,
            player_height=height, player_weight=weight,
            player_power=player_power, player_district=district,
            player_location=location, player_image=image
        )
        redirect_id = new_player.player_id

    # Redirect back to the same profile page
    return redirect("view_player_profile", player_id=redirect_id)

@login_required_custom
def add_position(request):
    """Add position - accessible to all logged-in users."""
    positions = Position.objects.all().order_by('-position_id')

    if request.method == "POST":
        table = Position()
        table.position_name = request.POST.get("pos_name")
        table.position_code = request.POST.get("pos_code")
        table.position_description = request.POST.get("pos_description")
        table.save()

        messages.success(request, f"Position '{table.position_name}' added successfully.")
        return render(request, "user/add_position.html", {"positions": positions})

    context = {"positions": positions}
    context.update(get_user_role_context(request))

    return render(request, "user/add_position.html", context)


@login_required_custom
def search_clubs(request):
    """Search clubs - accessible to all logged-in users."""
    query = request.GET.get("q", "")

    clubs = Club.objects.filter(
        Q(club_name__icontains=query) |
        Q(club_district__icontains=query),
        is_validated=True
    )

    data = []
    for club in clubs:
        data.append({
            "id": club.club_id,
            "name": club.club_name,
            "manager": club.club_manager.user_name,
            "location": club.club_location,
            "district": club.club_district,
            "ground": club.club_home_ground.turf_name if club.club_home_ground else "",
            "weight": club.club_weight,
            "logo": club.club_logo.url if club.club_logo else ""
        })

    return JsonResponse({"clubs": data})

@login_required_custom
def initiate_payment(request, booking_id):
    booking = get_object_or_404(Booking, booking_id=booking_id)

    if booking.status != "Accepted":
        return HttpResponse("<script>alert('Booking not approved yet.'); window.location.href='/user_app/turf_bookings/';</script>")

    amount = int(booking.turf.turf_rate * 100)

    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    order = client.order.create({
        'amount': amount,
        'currency': 'INR',
        'payment_capture': '1'
    })

    payment = Payment.objects.create(
        booking=booking,
        provider_order_id=order['id'],
        amount=amount
    )

    user = user_acc(request)
    if not user.user_email:
        user.user_email = f"user{user.user_id}@unfa.local"  # temporary 
        user.save()

    context = {
        'booking': booking,
        'payment': payment,
        'razorpay_key': settings.RAZORPAY_KEY_ID,
        'amount': amount,  
        'callback_url': settings.RAZORPAY_CALLBACK_URL,
        'debug': settings.DEBUG,
    }
    context.update(get_user_role_context(request))
    return render(request, 'club/payment.html', context)

@csrf_exempt
def payment_success(request):
    """Payment success callback (Razorpay webhook + redirect)."""
    if request.method != "POST":
        return HttpResponse("Invalid request", status=400)

    data = request.POST

    try:
        client = razorpay.Client(
            auth=(
                settings.RAZORPAY_KEY_ID,
                settings.RAZORPAY_KEY_SECRET
            )
        )

        params_dict = {
            'razorpay_order_id': data.get("razorpay_order_id"),
            'razorpay_payment_id': data.get("razorpay_payment_id"),
            'razorpay_signature': data.get("razorpay_signature")
        }

        client.utility.verify_payment_signature(params_dict)

        payment = Payment.objects.get(
            provider_order_id=data.get("razorpay_order_id")
        )

        payment.razorpay_payment_id = data.get("razorpay_payment_id")
        payment.signature_id = data.get("razorpay_signature")
        payment.payment_status = "Success"
        payment.save()

        booking = payment.booking
        booking.is_paid = True
        booking.save()

        # Create the Match ONLY after payment is confirmed
        home_club = Club.objects.filter(
            club_manager=booking.customer,
            is_validated=True
        ).first()

        # Get squad size from session or default to 5
        squad_size = request.session.get(
            'pending_squad_size',
            5
        )

        if 'pending_squad_size' in request.session:
            del request.session['pending_squad_size']

        match_time_range = str(
            booking.time_slot.tt_time.time_range
        ).strip()

        if "-" in match_time_range:
            match_start_time = (
                match_time_range
                .split("-", 1)[0]
                .strip()
            )
        else:
            match_start_time = match_time_range

        match, created = Match.objects.get_or_create(
            match_home_team=home_club,
            match_turf=booking.turf,
            match_date=booking.booking_date,
            match_time=match_start_time,
            defaults={
                "match_started": False,
                "match_finished": False,
                "squad_size": squad_size,
            }
        )

        create_notification(
            booking.customer,
            f"Payment successful! Match #{match.match_id} "
            f"at {booking.turf.turf_name} is confirmed.",
            'success'
        )

        create_notification(
            booking.turf.turf_owner,
            f"Payment received for booking at "
            f"{booking.turf.turf_name} on {booking.booking_date}.",
            'success'
        )

        messages.success(
            request,
            f"Payment successful! Match #{match.match_id} created."
        )

        # ---------------------------------------------------------
        # Squad selection
        # ---------------------------------------------------------
        if home_club:

            player_count = Player.objects.filter(
                player_club=home_club
            ).count()

            if player_count > squad_size:

                return redirect(
                    "select_squad",
                    match_id=match.match_id,
                    side="home"
                )

            else:

                all_players = Player.objects.filter(
                    player_club=home_club
                )

                match.home_squad.set(
                    all_players[:squad_size]
                )

                match.home_subs.set(
                    all_players[squad_size:]
                )

                match.home_squad_selected = True
                match.save()

                messages.success(
                    request,
                    "Home squad auto-assigned."
                )

        return redirect("club_matches")

    except razorpay.errors.SignatureVerificationError:

        messages.error(
            request,
            "Signature verification failed."
        )

        return redirect(
            "club_interface",
            club_id=request.session.get("current_club")
        )

    except Payment.DoesNotExist:

        messages.error(
            request,
            "Payment record not found."
        )

        return redirect("visitor_home")

@csrf_exempt
@csrf_exempt
def simulate_payment_success(request, booking_id):
    """DEVELOPMENT ONLY: Bypass Razorpay popup and simulate a successful payment."""

    if not settings.DEBUG:
        return HttpResponse(
            "Not allowed",
            status=403
        )

    booking = get_object_or_404(
        Booking,
        booking_id=booking_id
    )

    payment, _ = Payment.objects.get_or_create(
        booking=booking,
        defaults={
            'provider_order_id': f'test_order_{booking_id}',
            'amount': booking.turf.turf_rate * 100,
            'payment_status': 'Success'
        }
    )

    payment.razorpay_payment_id = f'test_pay_{booking_id}'
    payment.signature_id = 'test_signature'
    payment.payment_status = "Success"
    payment.save()

    booking.is_paid = True
    booking.save()

    home_club = Club.objects.filter(
        club_manager=booking.customer,
        is_validated=True
    ).first()

    # Get squad size from session or default to 5
    squad_size = request.session.get(
        'pending_squad_size',
        5
    )

    if 'pending_squad_size' in request.session:
        del request.session['pending_squad_size']

    match_time_range = str(
        booking.time_slot.tt_time.time_range
    ).strip()

    if "-" in match_time_range:
        match_start_time = (
            match_time_range
            .split("-", 1)[0]
            .strip()
        )
    else:
        match_start_time = match_time_range

    match, created = Match.objects.get_or_create(
        match_home_team=home_club,
        match_turf=booking.turf,
        match_date=booking.booking_date,
        match_time=match_start_time,
        defaults={
            "match_started": False,
            "match_finished": False,
            "squad_size": squad_size,
        }
    )

    create_notification(
        booking.customer,
        f"Test payment successful! "
        f"Match #{match.match_id} confirmed.",
        'success'
    )

    create_notification(
        booking.turf.turf_owner,
        f"Test payment received for booking at "
        f"{booking.turf.turf_name}.",
        'success'
    )

    messages.success(
        request,
        f"Test payment successful! "
        f"Match #{match.match_id} created."
    )

    # ---------------------------------------------------------
    # Squad selection
    # ---------------------------------------------------------
    if home_club:

        player_count = Player.objects.filter(
            player_club=home_club
        ).count()

        if player_count > squad_size:

            return redirect(
                "select_squad",
                match_id=match.match_id,
                side="home"
            )

        else:

            all_players = Player.objects.filter(
                player_club=home_club
            )

            match.home_squad.set(
                all_players[:squad_size]
            )

            match.home_subs.set(
                all_players[squad_size:]
            )

            match.home_squad_selected = True
            match.save()

    return redirect("club_matches")

@club_manager_required
def tournament(request):
    """Tournaments - shows ALL tournaments regardless of status."""
    user = user_acc(request)
    is_manager = check_manager(request)
    clubs = Club.objects.filter(club_manager=user, is_validated=True)

    
    tournaments = Tournament.objects.all().prefetch_related(
        't_club_map_set__t_c_club'
    ).select_related('t_host')

    # Get current time for template date comparisons
    now = timezone.now()

    # Get joined tournaments for the current user's club
    my_club = clubs.first()
    joined_tournaments = []
    if my_club:
        joined_tournaments = list(Tournament.objects.filter(
            t_club_map__t_c_club=my_club,
            t_club_map__is_paid=True
        ).values_list('t_id', flat=True))

    context = {
        "is_manager": is_manager,
        "tournaments": tournaments,
        "clubs": clubs,
        "now": now,  
        "joined_tournaments": joined_tournaments,
        "user": user,
    }
    context.update(get_user_role_context(request))

    return render(request, "club/tournaments.html", context)
@club_manager_required
def host_tournament(request):
    """Host a new tournament with fee and squad size configuration."""
    user = user_acc(request)
    club = get_object_or_404(Club, club_manager=user, is_validated=True)

    if request.method == "POST":
        t_name = request.POST.get("tournament_name")
        t_date = request.POST.get("tournament_date")
        registration_fee = request.POST.get("registration_fee", 0)
        prize_pool = request.POST.get("prize_pool", 0)
        max_teams = request.POST.get("max_teams", 16)
        registration_deadline = request.POST.get("registration_deadline")
        description = request.POST.get("description", "")
        format_type = request.POST.get("format", "hybrid")
        teams_per_group = request.POST.get("teams_per_group", 4)
        teams_qualifying = request.POST.get("teams_qualifying", 2)

        # NEW: Get squad size from form
        squad_size = int(request.POST.get("squad_size", 5))

        tournament = Tournament.objects.create(
            t_host=club,
            t_name=t_name,
            t_date=t_date,
            registration_fee=registration_fee,
            prize_pool=prize_pool if prize_pool else None,
            max_teams=max_teams,
            registration_deadline=registration_deadline if registration_deadline else None,
            description=description,
            format=format_type,
            teams_per_group=teams_per_group,
            teams_qualifying=teams_qualifying,
            squad_size=squad_size,
        )

        # Auto-register host club (free)
        T_club_map.objects.create(
            t_c_tournament=tournament,
            t_c_club=club,
            is_paid=True,
            payment_amount=0,
            paid_at=timezone.now()
        )

        create_notification(
            user,
            f"Tournament '{t_name}' hosted successfully! Format: {squad_size}-a-side. Registration fee: Rs.{registration_fee}",
            'success'
        )

        messages.success(request, f"Tournament '{t_name}' created successfully! ({squad_size}-a-side)")
        return redirect("tournament_list")

    context = {
        "is_manager": True,
        "today": date.today().isoformat(),
        "squad_sizes": [(5, '5-a-side'), (7, '7-a-side'), (9, '9-a-side'), (11, '11-a-side'), (12, '12-a-side')],
    }
    context.update(get_user_role_context(request))
    return render(request, "tournament/host_tournament.html", context)

@login_required_custom
def tournament_list(request):
    """View all tournaments - available to ALL logged-in users."""
    user = user_acc(request)
    now = timezone.now()

    all_tournaments = Tournament.objects.all().prefetch_related(
        't_club_map_set__t_c_club'
    ).select_related('t_host').order_by('t_date')

    upcoming_tournaments = all_tournaments.filter(
        t_date__gte=date.today(), is_active=True, is_completed=False
    )
    past_tournaments = all_tournaments.filter(is_completed=True)
    active_tournaments = all_tournaments.filter(
        is_active=True, is_completed=False, t_date__lte=date.today()
    )

    my_club = Club.objects.filter(club_manager=user, is_validated=True).first()
    my_registrations = []
    if my_club:
        my_registrations = list(T_club_map.objects.filter(
            t_c_club=my_club
        ).values_list('t_c_tournament_id', flat=True))

    context = {
        "tournaments": all_tournaments,
        "upcoming_tournaments": upcoming_tournaments,
        "past_tournaments": past_tournaments,
        "active_tournaments": active_tournaments,
        "my_registrations": my_registrations,
        "joined_tournaments": my_registrations,
        "is_manager": check_manager(request),
        "user": user,
        "now": now,
    }
    context.update(get_user_role_context(request))
    return render(request, "tournament/tournament_list.html", context)




@club_manager_required
def join_tournament(request, t_id):
    """Join tournament - redirect to payment if fee exists."""
    tournament = get_object_or_404(Tournament, t_id=t_id)
    user = user_acc(request)
    club = get_object_or_404(Club, club_manager=user, is_validated=True)

    # Check if tournament is full
    if tournament.is_full:
        messages.error(request, "This tournament is already full.")
        return redirect("view_tournament", t_id=t_id)

    # Check if already registered
    if T_club_map.objects.filter(t_c_tournament=tournament, t_c_club=club).exists():
        messages.warning(request, "Your club is already registered for this tournament.")
        return redirect("view_tournament", t_id=t_id)

    # Check deadline
    if tournament.registration_deadline and date.today() > tournament.registration_deadline:
        messages.error(request, "Registration deadline has passed.")
        return redirect("view_tournament", t_id=t_id)

    # If fee is required, redirect to payment
    if tournament.registration_fee > 0:
        return redirect("tournament_payment_initiate", t_id=t_id)

    # Free registration
    T_club_map.objects.create(
        t_c_tournament=tournament,
        t_c_club=club,
        is_paid=True,
        payment_amount=0,
        paid_at=timezone.now()
    )

    create_notification(
        user,
        f"Your club {club.club_name} has joined tournament '{tournament.t_name}'!",
        'success'
    )
    create_notification(
        tournament.t_host.club_manager,
        f"{club.club_name} has joined your tournament '{tournament.t_name}'!",
        'info'
    )

    messages.success(request, f"Successfully joined '{tournament.t_name}'!")
    return redirect("view_tournament", t_id=t_id)


@club_manager_required
def my_tournaments(request):
    user = user_acc(request)

    club = get_object_or_404(
        Club,
        club_manager=user,
        is_validated=True
    )

    tournaments = Tournament.objects.filter(
        t_host=club
    ).order_by('-t_date')

    context = {
        'tournaments': tournaments,
        'is_manager': True,
    }

    context.update(
        get_user_role_context(request)
    )

    return render(
        request,
        'tournament/my_tournaments.html',
        context
    )

@club_manager_required
def tournament_payment_initiate(request, t_id):
    """Initiate Razorpay payment for tournament registration."""

    tournament = get_object_or_404(
        Tournament,
        t_id=t_id
    )

    user = user_acc(request)

    club = get_object_or_404(
        Club,
        club_manager=user,
        is_validated=True
    )

    # ---------------------------------------------------------
    # Tournament status checks
    # ---------------------------------------------------------

    if tournament.is_completed:
        messages.error(
            request,
            "This tournament has already concluded."
        )
        return redirect(
            "view_tournament",
            t_id=t_id
        )

    # Check if tournament is full
    if tournament.is_full:
        messages.error(
            request,
            "This tournament is already full."
        )
        return redirect(
            "view_tournament",
            t_id=t_id
        )

    # Check registration deadline
    if (
        tournament.registration_deadline
        and date.today() > tournament.registration_deadline
    ):
        messages.error(
            request,
            "Registration deadline has passed."
        )
        return redirect(
            "view_tournament",
            t_id=t_id
        )

    # ---------------------------------------------------------
    # Check existing registration
    # ---------------------------------------------------------

    existing = T_club_map.objects.filter(
        t_c_tournament=tournament,
        t_c_club=club
    ).first()

    if existing and existing.is_paid:
        messages.warning(
            request,
            "Already registered and payment is completed."
        )
        return redirect(
            "view_tournament",
            t_id=t_id
        )

    # ---------------------------------------------------------
    # Make sure payment is actually required
    # ---------------------------------------------------------

    if tournament.registration_fee <= 0:
        messages.error(
            request,
            "This tournament does not require payment."
        )
        return redirect(
            "view_tournament",
            t_id=t_id
        )

    # ---------------------------------------------------------
    # Convert amount to paise
    # ---------------------------------------------------------

    amount = int(
        tournament.registration_fee * 100
    )

    # ---------------------------------------------------------
    # Razorpay client
    # ---------------------------------------------------------

    client = razorpay.Client(
        auth=(
            settings.RAZORPAY_KEY_ID,
            settings.RAZORPAY_KEY_SECRET
        )
    )

    # ---------------------------------------------------------
    # Create Razorpay order
    # ---------------------------------------------------------

    order = client.order.create({
        "amount": amount,
        "currency": "INR",
        "payment_capture": "1"
    })

    # ---------------------------------------------------------
    # Create or reuse tournament registration
    # ---------------------------------------------------------

    registration, created = T_club_map.objects.get_or_create(
        t_c_tournament=tournament,
        t_c_club=club,
        defaults={
            "payment_amount": tournament.registration_fee,
            "is_paid": False,
        }
    )

    # If pending registration already exists,
    # make sure the amount is up to date.
    if not created:
        registration.payment_amount = (
            tournament.registration_fee
        )
        registration.is_paid = False
        registration.save(
            update_fields=[
                "payment_amount",
                "is_paid"
            ]
        )

    # ---------------------------------------------------------
    # Create payment record
    # ---------------------------------------------------------

    payment = TournamentPayment.objects.create(
        tournament_registration=registration,
        provider_order_id=order["id"],
        amount=tournament.registration_fee
    )

    # ---------------------------------------------------------
    # Payment context
    #
    # IMPORTANT:
    # Keep the variable name "razorpay_key".
    # Your existing tournament_payment.html expects this.
    # ---------------------------------------------------------

    context = {
        "tournament": tournament,
        "club": club,
        "registration": registration,
        "payment": payment,

        # IMPORTANT — DO NOT rename this to razorpay_key_id
        "razorpay_key": settings.RAZORPAY_KEY_ID,

        # Razorpay expects amount in paise
        "amount": amount,

        # Callback URL used by your existing payment template
        "callback_url": request.build_absolute_uri(
            reverse(
                "tournament_payment_success",
                kwargs={
                    "tp_id": payment.tp_id
                }
            )
        ),
    }

    context.update(
        get_user_role_context(request)
    )

    return render(
        request,
        "tournament/tournament_payment.html",
        context
    )

@csrf_exempt
def tournament_payment_success(request, tp_id):
    """Handle tournament payment success."""
    if request.method != "POST":
        return HttpResponse("Invalid request", status=400)

    data = request.POST
    try:
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        params_dict = {
            'razorpay_order_id': data.get("razorpay_order_id"),
            'razorpay_payment_id': data.get("razorpay_payment_id"),
            'razorpay_signature': data.get("razorpay_signature")
        }
        client.utility.verify_payment_signature(params_dict)

        payment = TournamentPayment.objects.get(provider_order_id=data.get("razorpay_order_id"))
        payment.razorpay_payment_id = data.get("razorpay_payment_id")
        payment.signature_id = data.get("razorpay_signature")
        payment.payment_status = "Success"
        payment.save()

        # Update registration
        registration = payment.tournament_registration
        registration.is_paid = True
        registration.paid_at = timezone.now()
        registration.save()

        tournament = registration.t_c_tournament
        club = registration.t_c_club

        create_notification(
            club.club_manager,
            f"Payment successful! Your club {club.club_name} is now registered in '{tournament.t_name}'.",
            'success'
        )
        create_notification(
            tournament.t_host.club_manager,
            f"{club.club_name} has completed payment and joined '{tournament.t_name}'.",
            'success'
        )

        messages.success(request, "Payment successful! You are now registered for the tournament.")
        return redirect("view_tournament", t_id=tournament.t_id)

    except razorpay.errors.SignatureVerificationError:
        messages.error(request, "Signature verification failed.")
        return redirect("tournament_list")
    except TournamentPayment.DoesNotExist:
        messages.error(request, "Payment record not found.")
        return redirect("tournament_list")


@csrf_exempt
def simulate_tournament_payment(request, t_id):
    """DEVELOPMENT ONLY: Simulate tournament payment."""
    if not settings.DEBUG:
        return HttpResponse("Not allowed", status=403)

    tournament = get_object_or_404(Tournament, t_id=t_id)
    user = user_acc(request)
    club = get_object_or_404(Club, club_manager=user, is_validated=True)

    registration, created = T_club_map.objects.get_or_create(
        t_c_tournament=tournament,
        t_c_club=club,
        defaults={'payment_amount': tournament.registration_fee}
    )

    TournamentPayment.objects.create(
        tournament_registration=registration,
        provider_order_id=f'test_tour_{tournament.t_id}_{club.club_id}',
        razorpay_payment_id=f'test_pay_tour_{tournament.t_id}',
        signature_id='test_signature',
        payment_status='Success',
        amount=tournament.registration_fee
    )

    registration.is_paid = True
    registration.paid_at = timezone.now()
    registration.save()

    messages.success(request, f"Test payment successful! Registered for '{tournament.t_name}'.")
    return redirect("view_tournament", t_id=t_id)



@club_manager_required
def update_tournament_stats(request, t_id):
    """Recalculate all tournament stats. Trigger after match results."""
    tournament = get_object_or_404(Tournament, t_id=t_id)

    registrations = T_club_map.objects.filter(t_c_tournament=tournament)
    for reg in registrations:
        reg.update_stats()

    messages.success(request, "Tournament statistics updated successfully.")
    return redirect("view_tournament", t_id=t_id)


@club_manager_required
def leave_tournament(request, t_id):
    """Allow a club to leave tournament before it starts."""
    tournament = get_object_or_404(Tournament, t_id=t_id)
    user = user_acc(request)
    club = get_object_or_404(Club, club_manager=user, is_validated=True)

    if Match.objects.filter(tournament=tournament, match_started=True).exists():
        messages.error(request, "Cannot leave after matches have started.")
        return redirect("view_tournament", t_id=t_id)

    # Also cannot leave if tournament is completed
    if tournament.is_completed:
        messages.error(request, "This tournament has already concluded.")
        return redirect("view_tournament", t_id=t_id)

    registration = T_club_map.objects.filter(t_c_tournament=tournament, t_c_club=club).first()
    if registration:
        registration.delete()
        create_notification(
            user,
            f"Your club has left tournament '{tournament.t_name}'.",
            'info'
        )
        messages.success(request, "You have left the tournament.")
    else:
        messages.warning(request, "You are not registered in this tournament.")

    return redirect("tournament_list")

@club_manager_required
def edit_tournament(request, t_id):
    """Safely edit a tournament while preserving existing registrations, payments and fixtures."""
    tournament = get_object_or_404(Tournament, t_id=t_id)
    user = user_acc(request)

    if not tournament.t_host or tournament.t_host.club_manager != user:
        messages.error(request, "Only the tournament host can edit this tournament.")
        return redirect("view_tournament", t_id=t_id)

    registrations = T_club_map.objects.filter(t_c_tournament=tournament)
    registered_count = registrations.count()
    paid_count = registrations.filter(is_paid=True).count()

    has_registrations = registered_count > 0
    has_paid_registrations = paid_count > 0
    has_matches = Match.objects.filter(tournament=tournament).exists()
    matches_started = Match.objects.filter(
        tournament=tournament, match_started=True
    ).exists()

    if matches_started:
        messages.error(request, "Cannot edit tournament after matches have started.")
        return redirect("view_tournament", t_id=t_id)

    structure_locked = has_matches
    date_locked = has_matches
    fee_locked = has_paid_registrations and registered_count > 1

    if request.method == "POST":
        tournament_name = request.POST.get("tournament_name", "").strip()
        description = request.POST.get("description", "").strip()

        if not tournament_name:
            messages.error(request, "Tournament name is required.")
            return redirect("edit_tournament", t_id=t_id)

        if date_locked:
            tournament_date = tournament.t_date
        else:
            raw = request.POST.get("tournament_date", "").strip()
            try:
                tournament_date = datetime.strptime(raw, "%Y-%m-%d").date()
            except (TypeError, ValueError):
                messages.error(request, "Tournament date must be a valid date.")
                return redirect("edit_tournament", t_id=t_id)

        deadline_raw = request.POST.get("registration_deadline", "").strip()
        if deadline_raw:
            try:
                registration_deadline = datetime.strptime(
                    deadline_raw, "%Y-%m-%d"
                ).date()
            except (TypeError, ValueError):
                messages.error(request, "Registration deadline must be a valid date.")
                return redirect("edit_tournament", t_id=t_id)
        else:
            registration_deadline = None

        if registration_deadline and tournament_date:
            if registration_deadline > tournament_date:
                messages.error(
                    request,
                    "Registration deadline cannot be after the tournament date."
                )
                return redirect("edit_tournament", t_id=t_id)

        if fee_locked:
            registration_fee = tournament.registration_fee
        else:
            try:
                registration_fee = Decimal(
                    request.POST.get("registration_fee", "0") or "0"
                )
            except (InvalidOperation, TypeError, ValueError):
                messages.error(request, "Registration fee must be a valid number.")
                return redirect("edit_tournament", t_id=t_id)

            if registration_fee < 0:
                messages.error(request, "Registration fee cannot be negative.")
                return redirect("edit_tournament", t_id=t_id)

        try:
            prize_pool = Decimal(
                request.POST.get("prize_pool", "0") or "0"
            )
        except (InvalidOperation, TypeError, ValueError):
            messages.error(request, "Prize pool must be a valid number.")
            return redirect("edit_tournament", t_id=t_id)

        if prize_pool < 0:
            messages.error(request, "Prize pool cannot be negative.")
            return redirect("edit_tournament", t_id=t_id)

        if structure_locked:
            max_teams = tournament.max_teams
            format_type = tournament.format
            teams_per_group = tournament.teams_per_group
            teams_qualifying = tournament.teams_qualifying
            squad_size = tournament.squad_size
        else:
            format_type = request.POST.get("format", tournament.format or "hybrid").strip().lower()
            if format_type not in {"league", "knockout", "hybrid"}:
                messages.error(request, "Invalid tournament format selected.")
                return redirect("edit_tournament", t_id=t_id)

            try:
                max_teams = int(request.POST.get("max_teams", tournament.max_teams))
                teams_per_group = int(request.POST.get("teams_per_group", tournament.teams_per_group))
                teams_qualifying = int(request.POST.get("teams_qualifying", tournament.teams_qualifying))
                squad_size = int(request.POST.get("squad_size", tournament.squad_size))
            except (TypeError, ValueError):
                messages.error(request, "Tournament configuration contains an invalid number.")
                return redirect("edit_tournament", t_id=t_id)

            if max_teams < 2:
                messages.error(request, "Tournament must allow at least 2 teams.")
                return redirect("edit_tournament", t_id=t_id)

            if max_teams < registered_count:
                messages.error(
                    request,
                    f"Maximum teams cannot be less than the {registered_count} registered club(s)."
                )
                return redirect("edit_tournament", t_id=t_id)

            if teams_per_group < 2:
                messages.error(request, "A group must contain at least 2 teams.")
                return redirect("edit_tournament", t_id=t_id)

            if teams_qualifying < 1 or teams_qualifying >= teams_per_group:
                messages.error(
                    request,
                    "Teams qualifying from a group must be at least 1 and less than the group size."
                )
                return redirect("edit_tournament", t_id=t_id)

            if format_type == "hybrid" and registered_count < teams_per_group:
                pass

            if squad_size not in {5, 7, 9, 11, 12}:
                messages.error(request, "Invalid squad size selected.")
                return redirect("edit_tournament", t_id=t_id)

        is_active = request.POST.get("is_active") == "on"
        with transaction.atomic():
            tournament.t_name = tournament_name
            tournament.t_date = tournament_date
            tournament.registration_fee = registration_fee
            tournament.prize_pool = prize_pool
            tournament.registration_deadline = registration_deadline
            tournament.description = description
            tournament.is_active = is_active

            if not structure_locked:
                tournament.max_teams = max_teams
                tournament.format = format_type
                tournament.teams_per_group = teams_per_group
                tournament.teams_qualifying = teams_qualifying
                tournament.squad_size = squad_size

            tournament.save()

        # IMPORTANT: no fixture deletion/re-generation happens here.
        # Editing the tournament must not destroy existing club registrations.

        create_notification(
            user,
            f"Tournament '{tournament.t_name}' was updated successfully.",
            "success"
        )
        messages.success(request, "Tournament updated successfully.")
        return redirect("view_tournament", t_id=t_id)

    context = {
        "tournament": tournament,
        "today": date.today().isoformat(),
        "registered_count": registered_count,
        "paid_count": paid_count,
        "has_registrations": has_registrations,
        "has_paid_registrations": has_paid_registrations,
        "has_matches": has_matches,
        "matches_started": matches_started,
        "structure_locked": structure_locked,
        "date_locked": date_locked,
        "fee_locked": fee_locked,
        "squad_sizes": [
            (5, "5-a-side"),
            (7, "7-a-side"),
            (9, "9-a-side"),
            (11, "11-a-side"),
            (12, "12-a-side"),
        ],
        "format_choices": Tournament.FORMAT_CHOICES,
    }
    context.update(get_user_role_context(request))

    return render(request, "tournament/edit_tournament.html", context)
@club_manager_required
def delete_tournament(request, t_id):
    """Delete tournament (host only, before matches start)."""
    tournament = get_object_or_404(Tournament, t_id=t_id)
    user = user_acc(request)

    if tournament.t_host.club_manager != user:
        messages.error(request, "Only the host can delete this tournament.")
        return redirect("view_tournament", t_id=t_id)

    if Match.objects.filter(tournament=tournament, match_started=True).exists():
        messages.error(request, "Cannot delete tournament after matches have started.")
        return redirect("view_tournament", t_id=t_id)

    tournament_name = tournament.t_name
    tournament.delete()

    create_notification(
        user,
        f"Tournament '{tournament_name}' has been deleted.",
        'info'
    )
    messages.success(request, f"Tournament '{tournament_name}' deleted successfully.")
    return redirect("tournament_list")

def _generate_round_robin(tournament, clubs):

    n = len(clubs)

    tournament_turf = (
        tournament.t_host.club_home_ground
        or Turf.objects.filter(is_validated=True).first()
    )

    for i in range(n):
        for j in range(i + 1, n):

            Match.objects.create(
                tournament=tournament,
                match_home_team=clubs[i],
                match_away_team=clubs[j],
                match_turf=tournament_turf,
                match_date=tournament.t_date,
                match_time=None,
                round_number=1,
                is_knockout=False,
                squad_size=tournament.squad_size,
            )

def _generate_hybrid(
    tournament,
    clubs,
    teams_per_group,
    teams_qualifying
):
    """
    Generate:

        GROUP STAGE
            ↓
        QUALIFIED TEAMS
            ↓
        COMPLETE KNOCKOUT BRACKET
            ↓
        FINAL

    Hybrid round numbering:

        Round 1 = Group Stage
        Round 2+ = Knockout Stage
    """

    clubs = list(clubs)

    if len(clubs) < 2:
        return

    if teams_per_group < 2:
        raise ValueError(
            "Teams per group must be at least 2."
        )

    if teams_qualifying < 1:
        raise ValueError(
            "Teams qualifying must be at least 1."
        )

    # ---------------------------------------------------------
    # TOURNAMENT TURF
    # ---------------------------------------------------------

    tournament_turf = (
        tournament.t_host.club_home_ground
        if tournament.t_host
        and tournament.t_host.club_home_ground
        else Turf.objects.filter(is_validated=True).first()
    )

    if not tournament_turf:
        raise ValueError(
            "No valid turf is available for this tournament."
        )

    # ---------------------------------------------------------
    # SHUFFLE CLUBS
    # ---------------------------------------------------------

    random.shuffle(clubs)

    number_of_clubs = len(clubs)

    # ---------------------------------------------------------
    # NUMBER OF GROUPS
    # ---------------------------------------------------------

    number_of_groups = (
        number_of_clubs + teams_per_group - 1
    ) // teams_per_group

    group_names = [
        chr(65 + i)
        for i in range(number_of_groups)
    ]

    # ---------------------------------------------------------
    # ASSIGN CLUBS TO GROUPS
    # ---------------------------------------------------------

    for index, club in enumerate(clubs):

        group_index = index // teams_per_group

        group_name = group_names[group_index]

        registration = T_club_map.objects.get(
            t_c_tournament=tournament,
            t_c_club=club
        )

        registration.group_name = group_name

        registration.save(
            update_fields=["group_name"]
        )

    # ---------------------------------------------------------
    # CREATE GROUP-STAGE MATCHES
    # ---------------------------------------------------------

    for group_name in group_names:

        group_clubs = list(
            T_club_map.objects.filter(
                t_c_tournament=tournament,
                group_name=group_name
            )
            .select_related("t_c_club")
            .values_list("t_c_club", flat=True)
        )

        for i in range(len(group_clubs)):

            for j in range(i + 1, len(group_clubs)):

                Match.objects.create(
                    tournament=tournament,

                    match_home_team_id=group_clubs[i],
                    match_away_team_id=group_clubs[j],

                    match_turf=tournament_turf,

                    match_date=tournament.t_date,
                    match_time=None,

                    round_number=1,
                    is_knockout=False,

                    squad_size=tournament.squad_size,

                    match_started=False,
                    match_finished=False,
                )

    # ---------------------------------------------------------
    # DETERMINE ACTUAL POSSIBLE QUALIFIERS
    # ---------------------------------------------------------

    total_qualifying = 0

    for group_name in group_names:

        group_count = (
            T_club_map.objects.filter(
                t_c_tournament=tournament,
                group_name=group_name
            ).count()
        )

        total_qualifying += min(
            teams_qualifying,
            group_count
        )

    # Need at least two teams for knockout.
    if total_qualifying < 2:
        return

    # ---------------------------------------------------------
    # FIND POWER-OF-TWO BRACKET SIZE
    # ---------------------------------------------------------

    bracket_size = 1

    while bracket_size < total_qualifying:
        bracket_size *= 2

    # ---------------------------------------------------------
    # NUMBER OF BYES
    # ---------------------------------------------------------

    number_of_byes = (
        bracket_size - total_qualifying
    )

    # ---------------------------------------------------------
    # CREATE FIRST KNOCKOUT ROUND
    #
    # Hybrid:
    # Round 1 = groups
    # Round 2 = first knockout round
    # ---------------------------------------------------------

    first_knockout_round = 2

    first_round_match_count = (
        bracket_size // 2
    )

    first_round_matches = []

    for bracket_position in range(
        first_round_match_count
    ):

        match = Match.objects.create(
            tournament=tournament,

            match_home_team=None,
            match_away_team=None,

            match_turf=tournament_turf,

            match_date=(
                tournament.t_date
                + timedelta(days=2)
            ),

            match_time=None,

            round_number=first_knockout_round,
            is_knockout=True,
            bracket_position=bracket_position,

            squad_size=tournament.squad_size,

            match_started=False,
            match_finished=False,
        )

        first_round_matches.append(match)

    # ---------------------------------------------------------
    # CREATE ALL REMAINING KNOCKOUT ROUNDS
    # ---------------------------------------------------------

    current_match_count = first_round_match_count

    round_number = (
        first_knockout_round + 1
    )

    while current_match_count > 1:

        current_match_count //= 2

        for bracket_position in range(
            current_match_count
        ):

            Match.objects.create(
                tournament=tournament,

                match_home_team=None,
                match_away_team=None,

                match_turf=tournament_turf,

                match_date=(
                    tournament.t_date
                    + timedelta(
                        days=round_number
                    )
                ),

                match_time=None,

                round_number=round_number,
                is_knockout=True,
                bracket_position=bracket_position,

                squad_size=tournament.squad_size,

                match_started=False,
                match_finished=False,
            )

        round_number += 1


# ============================================================
# TOURNAMENT FIXTURE GENERATION
# ============================================================

def _get_tournament_turf(tournament):
    """
    Get the tournament host's home ground first.
    Fall back to the first validated turf.
    """

    if (
        tournament.t_host
        and tournament.t_host.club_home_ground
    ):
        return tournament.t_host.club_home_ground

    return Turf.objects.filter(
        is_validated=True
    ).first()


def _generate_round_robin(tournament, clubs):
    """
    League / Round Robin tournament.

    Every club plays every other club once.
    """

    clubs = list(clubs)

    if len(clubs) < 2:
        return

    tournament_turf = _get_tournament_turf(tournament)

    if not tournament_turf:
        raise ValueError(
            "No valid turf is available for this tournament."
        )

    for i in range(len(clubs)):

        for j in range(i + 1, len(clubs)):

            Match.objects.create(
                tournament=tournament,

                match_home_team=clubs[i],
                match_away_team=clubs[j],

                match_turf=tournament_turf,

                match_date=tournament.t_date,
                match_time=None,

                round_number=1,

                is_knockout=False,

                bracket_position=0,

                squad_size=tournament.squad_size,

                match_started=False,
                match_finished=False,
            )


def _generate_hybrid(
    tournament,
    clubs,
    teams_per_group,
    teams_qualifying
):
    """
    HYBRID TOURNAMENT

    IMPORTANT:
    This function creates ONLY the group stage.

    It MUST NOT create knockout matches.

    Knockout matches are created later by
    populate_hybrid_knockout() after every group
    match has finished.
    """

    clubs = list(clubs)

    if len(clubs) < 2:
        return

    if teams_per_group < 2:
        raise ValueError(
            "Teams per group must be at least 2."
        )

    if teams_qualifying < 1:
        raise ValueError(
            "Teams qualifying per group must be at least 1."
        )

    if teams_qualifying >= teams_per_group:
        raise ValueError(
            "Teams qualifying per group must be less than "
            "the number of teams in each group."
        )

    random.shuffle(clubs)

    # --------------------------------------------------------
    # NUMBER OF GROUPS
    # --------------------------------------------------------

    num_groups = (
        len(clubs) + teams_per_group - 1
    ) // teams_per_group

    group_names = [
        chr(65 + i)
        for i in range(num_groups)
    ]

    tournament_turf = _get_tournament_turf(tournament)

    if not tournament_turf:
        raise ValueError(
            "No valid turf is available for this tournament."
        )

    # --------------------------------------------------------
    # ASSIGN CLUBS TO GROUPS
    # --------------------------------------------------------

    for index, club in enumerate(clubs):

        group_index = (
            index // teams_per_group
        )

        group_name = group_names[
            min(
                group_index,
                len(group_names) - 1
            )
        ]

        registration = T_club_map.objects.get(
            t_c_tournament=tournament,
            t_c_club=club
        )

        registration.group_name = group_name

        registration.save(
            update_fields=[
                "group_name"
            ]
        )

    # --------------------------------------------------------
    # CREATE GROUP MATCHES ONLY
    # --------------------------------------------------------

    for group_name in group_names:

        group_clubs = list(
            T_club_map.objects.filter(
                t_c_tournament=tournament,
                group_name=group_name
            )
            .select_related("t_c_club")
            .values_list(
                "t_c_club",
                flat=True
            )
        )

        for i in range(len(group_clubs)):

            for j in range(
                i + 1,
                len(group_clubs)
            ):

                Match.objects.create(
                    tournament=tournament,

                    match_home_team_id=group_clubs[i],
                    match_away_team_id=group_clubs[j],

                    match_turf=tournament_turf,

                    match_date=tournament.t_date,
                    match_time=None,

                    # Hybrid group stage
                    round_number=1,
                    is_knockout=False,

                    bracket_position=0,

                    squad_size=tournament.squad_size,

                    match_started=False,
                    match_finished=False,
                )

    # --------------------------------------------------------
    # DO NOT CREATE KNOCKOUT MATCHES HERE
    # --------------------------------------------------------
    #
    # The knockout stage is created only after ALL
    # group matches are finished.
    #
    # --------------------------------------------------------


def _generate_knockout(tournament, clubs):
    """
    Standalone single-elimination knockout tournament.

    This creates:
        - First knockout round
        - All future rounds
        - BYE advancement
    """

    clubs = list(clubs)

    if len(clubs) < 2:
        return

    tournament_turf = _get_tournament_turf(tournament)

    if not tournament_turf:
        raise ValueError(
            "No valid turf is available for this tournament."
        )

    random.shuffle(clubs)

    number_of_clubs = len(clubs)

    # --------------------------------------------------------
    # POWER OF TWO BRACKET
    # --------------------------------------------------------

    bracket_size = 1

    while bracket_size < number_of_clubs:
        bracket_size *= 2

    number_of_byes = (
        bracket_size - number_of_clubs
    )

    slots = (
        clubs +
        [None] * number_of_byes
    )

    random.shuffle(slots)

    # --------------------------------------------------------
    # FIRST ROUND
    # --------------------------------------------------------

    round_number = 1

    matches_in_round = (
        bracket_size // 2
    )

    first_round_matches = []

    for bracket_position in range(
        matches_in_round
    ):

        home_team = slots[
            bracket_position * 2
        ]

        away_team = slots[
            bracket_position * 2 + 1
        ]

        match = Match.objects.create(
            tournament=tournament,

            match_home_team=home_team,
            match_away_team=away_team,

            match_turf=tournament_turf,

            match_date=(
                tournament.t_date
                + timedelta(
                    days=round_number - 1
                )
            ),

            match_time=None,

            round_number=round_number,

            is_knockout=True,

            bracket_position=bracket_position,

            squad_size=tournament.squad_size,

            match_started=False,
            match_finished=False,
        )

        first_round_matches.append(match)

    # --------------------------------------------------------
    # FUTURE ROUNDS
    # --------------------------------------------------------

    current_matches = matches_in_round

    round_number += 1

    while current_matches > 1:

        current_matches //= 2

        for bracket_position in range(
            current_matches
        ):

            Match.objects.create(
                tournament=tournament,

                match_home_team=None,
                match_away_team=None,

                match_turf=tournament_turf,

                match_date=(
                    tournament.t_date
                    + timedelta(
                        days=round_number - 1
                    )
                ),

                match_time=None,

                round_number=round_number,

                is_knockout=True,

                bracket_position=bracket_position,

                squad_size=tournament.squad_size,

                match_started=False,
                match_finished=False,
            )

        round_number += 1

    # --------------------------------------------------------
    # PROCESS BYES
    # --------------------------------------------------------

    for match in first_round_matches:

        has_home = (
            match.match_home_team
            is not None
        )

        has_away = (
            match.match_away_team
            is not None
        )

        # Normal match
        if has_home and has_away:
            continue

        # Completely empty match
        if not has_home and not has_away:
            continue

        # ----------------------------------------------------
        # BYE
        # ----------------------------------------------------

        match.match_finished = True
        match.match_started = False

        match.save(
            update_fields=[
                "match_finished",
                "match_started",
            ]
        )

        advance_knockout_winner(match)


# ============================================================
# HYBRID KNOCKOUT CREATION
# ============================================================

def populate_hybrid_knockout(tournament):
    """
    Create the knockout bracket for a hybrid tournament.

    This function does NOTHING until every group-stage match
    has been completed.
    """

    if tournament.format != "hybrid":
        return False

    # --------------------------------------------------------
    # GET GROUP MATCHES
    # --------------------------------------------------------

    group_matches = Match.objects.filter(
        tournament=tournament,
        is_knockout=False
    )

    if not group_matches.exists():
        return False

    # --------------------------------------------------------
    # GROUP STAGE MUST BE 100% COMPLETE
    # --------------------------------------------------------

    unfinished_group_matches = group_matches.filter(
        match_finished=False
    )

    if unfinished_group_matches.exists():
        return False

    # --------------------------------------------------------
    # PREVENT DUPLICATE BRACKETS
    # --------------------------------------------------------

    if Match.objects.filter(
        tournament=tournament,
        is_knockout=True
    ).exists():

        return True

    # --------------------------------------------------------
    # UPDATE ALL GROUP STATISTICS
    # --------------------------------------------------------

    registrations = T_club_map.objects.filter(
        t_c_tournament=tournament
    )

    for registration in registrations:
        registration.update_stats()

    # --------------------------------------------------------
    # GET GROUPS
    # --------------------------------------------------------

    groups = (
        T_club_map.objects
        .filter(
            t_c_tournament=tournament,
            group_name__isnull=False
        )
        .values_list(
            "group_name",
            flat=True
        )
        .distinct()
        .order_by("group_name")
    )

    qualified_clubs = []

    # --------------------------------------------------------
    # SELECT QUALIFIERS
    # --------------------------------------------------------

    for group_name in groups:

        group_teams = list(
            T_club_map.objects
            .filter(
                t_c_tournament=tournament,
                group_name=group_name
            )
            .select_related("t_c_club")
            .order_by(
                "-points",
                "-goals_for",
                "goals_against",
                "t_c_club__club_name"
            )
        )

        qualifiers = group_teams[
            :tournament.teams_qualifying
        ]

        for registration in qualifiers:

            if registration.t_c_club:

                qualified_clubs.append(
                    registration.t_c_club
                )

    # --------------------------------------------------------
    # NEED AT LEAST TWO QUALIFIERS
    # --------------------------------------------------------

    if len(qualified_clubs) < 2:
        return False

    # --------------------------------------------------------
    # CREATE POWER-OF-TWO BRACKET
    # --------------------------------------------------------

    clubs = list(qualified_clubs)

    random.shuffle(clubs)

    number_of_clubs = len(clubs)

    bracket_size = 1

    while bracket_size < number_of_clubs:
        bracket_size *= 2

    number_of_byes = (
        bracket_size - number_of_clubs
    )

    slots = (
        clubs +
        [None] * number_of_byes
    )

    random.shuffle(slots)

    tournament_turf = _get_tournament_turf(
        tournament
    )

    if not tournament_turf:
        raise ValueError(
            "No valid turf is available for this tournament."
        )

    # --------------------------------------------------------
    # HYBRID ROUND NUMBERS
    #
    # round 1 = Group Stage
    # round 2 = first knockout round
    # round 3 = next knockout round
    # ...
    # --------------------------------------------------------

    first_knockout_round = 2

    matches_in_round = (
        bracket_size // 2
    )

    first_round_matches = []

    # --------------------------------------------------------
    # FIRST KNOCKOUT ROUND
    # --------------------------------------------------------

    for bracket_position in range(
        matches_in_round
    ):

        home_team = slots[
            bracket_position * 2
        ]

        away_team = slots[
            bracket_position * 2 + 1
        ]

        match = Match.objects.create(
            tournament=tournament,

            match_home_team=home_team,
            match_away_team=away_team,

            match_turf=tournament_turf,

            match_date=(
                tournament.t_date
                + timedelta(days=1)
            ),

            match_time=None,

            round_number=first_knockout_round,

            is_knockout=True,

            bracket_position=bracket_position,

            squad_size=tournament.squad_size,

            match_started=False,
            match_finished=False,
        )

        first_round_matches.append(match)

    # --------------------------------------------------------
    # CREATE ALL FUTURE KNOCKOUT ROUNDS
    # --------------------------------------------------------

    current_matches = matches_in_round

    round_number = (
        first_knockout_round + 1
    )

    while current_matches > 1:

        current_matches //= 2

        for bracket_position in range(
            current_matches
        ):

            Match.objects.create(
                tournament=tournament,

                match_home_team=None,
                match_away_team=None,

                match_turf=tournament_turf,

                match_date=(
                    tournament.t_date
                    + timedelta(
                        days=round_number - 1
                    )
                ),

                match_time=None,

                round_number=round_number,

                is_knockout=True,

                bracket_position=bracket_position,

                squad_size=tournament.squad_size,

                match_started=False,
                match_finished=False,
            )

        round_number += 1

    # --------------------------------------------------------
    # PROCESS BYES
    # --------------------------------------------------------

    for match in first_round_matches:

        has_home = (
            match.match_home_team
            is not None
        )

        has_away = (
            match.match_away_team
            is not None
        )

        # Normal match
        if has_home and has_away:
            continue

        # Empty match
        if not has_home and not has_away:
            continue

        # BYE
        match.match_finished = True
        match.match_started = False

        match.save(
            update_fields=[
                "match_finished",
                "match_started",
            ]
        )

        advance_knockout_winner(match)

    return True

# ============================================================
# KNOCKOUT WINNER ADVANCEMENT
# ============================================================

def advance_knockout_winner(match):
    """
    Advance a completed knockout match winner.

    Handles:
        - Normal knockout matches
        - BYE matches
        - TBD matches
        - Hybrid brackets
        - Standalone knockout brackets
    """

    if not match.is_knockout:
        return None

    if not match.match_finished:
        return None

    # --------------------------------------------------------
    # DETERMINE WINNER
    # --------------------------------------------------------

    winner = None

    # --------------------------------------------------------
    # HOME BYE
    # --------------------------------------------------------

    if (
        match.match_home_team is not None
        and match.match_away_team is None
    ):

        winner = match.match_home_team

    # --------------------------------------------------------
    # AWAY BYE
    # --------------------------------------------------------

    elif (
        match.match_home_team is None
        and match.match_away_team is not None
    ):

        winner = match.match_away_team

    # --------------------------------------------------------
    # TBD MATCH
    # --------------------------------------------------------

    elif (
        match.match_home_team is None
        or match.match_away_team is None
    ):

        return None

    # --------------------------------------------------------
    # NORMAL MATCH
    # --------------------------------------------------------

    else:

        result = (
            Result.objects
            .filter(
                result_match=match
            )
            .first()
        )

        if not result:
            return None

        # HOME WIN
        if (
            result.result_home_team
            > result.result_away_team
        ):

            winner = match.match_home_team

        # AWAY WIN
        elif (
            result.result_away_team
            > result.result_home_team
        ):

            winner = match.match_away_team

        # DRAW
        #
        # Result model currently has no penalty-winner
        # field, so do not advance anybody.
        #
        else:

            return None

    if winner is None:
        return None

    # --------------------------------------------------------
    # CHECK WHETHER THIS IS THE FINAL
    # --------------------------------------------------------

    next_round = (
        match.round_number + 1
    )

    next_bracket_position = (
        match.bracket_position // 2
    )

    # --------------------------------------------------------
    # FIND NEXT MATCH
    # --------------------------------------------------------

    next_match = (
        Match.objects
        .filter(
            tournament=match.tournament,
            is_knockout=True,
            round_number=next_round,
            bracket_position=next_bracket_position
        )
        .first()
    )

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    if not next_match:
        return winner

    # --------------------------------------------------------
    # DETERMINE SLOT
    # --------------------------------------------------------

    if (
        match.bracket_position % 2 == 0
    ):

        # First source match -> home
        next_match.match_home_team = winner

    else:

        # Second source match -> away
        next_match.match_away_team = winner

    next_match.save(
        update_fields=[
            "match_home_team",
            "match_away_team",
        ]
    )

    # IMPORTANT:
    # Do NOT mark the next match as finished merely because
    # one finalist has arrived. In a normal knockout bracket,
    # the other slot is still waiting for the other feeder match.
    #
    # Real BYEs are already processed when the first-round bracket
    # is generated. They advance through this function without
    # prematurely finishing a future match.

    return winner

@login_required_custom
def view_tournament(request, t_id):
    """
    Display tournament details, standings and Match Center.

    Match Center data is normalized into dictionaries containing:
        {
            "match": Match instance,
            "result": Result instance or None,
            "is_completed": bool,
        }

    This keeps the template consistent for:
        - League matches
        - Hybrid group matches
        - Knockout matches
    """

    # =========================================================
    # TOURNAMENT
    # =========================================================

    tournament = get_object_or_404(
        Tournament,
        t_id=t_id
    )

    user = user_acc(request)

    # =========================================================
    # USER / CLUB
    # =========================================================

    is_manager = check_manager(request)

    my_club = (
        Club.objects
        .filter(
            club_manager=user,
            is_validated=True
        )
        .first()
    )

    # =========================================================
    # REGISTRATION STATUS
    # =========================================================

    is_registered = False
    my_registration = None
    registration_pending_payment = False

    if my_club:

        my_registration = (
            T_club_map.objects
            .filter(
                t_c_tournament=tournament,
                t_c_club=my_club
            )
            .first()
        )

        is_registered = (
            my_registration is not None
        )

        if (
            my_registration
            and not my_registration.is_paid
            and tournament.registration_fee > 0
        ):
            registration_pending_payment = True

    # =========================================================
    # UPDATE TOURNAMENT STATISTICS
    # =========================================================
    #
    # This keeps standings synchronized with finished matches.
    #

    all_registrations = (
        T_club_map.objects
        .filter(
            t_c_tournament=tournament
        )
    )

    for registration in all_registrations:
        registration.update_stats()

    # =========================================================
    # ALL REGISTRATIONS
    # =========================================================

    registrations = (
        T_club_map.objects
        .filter(
            t_c_tournament=tournament
        )
        .select_related(
            "t_c_club"
        )
        .order_by(
            "-points",
            "-goals_for",
            "goals_against",
            "t_c_club__club_name"
        )
    )

    # =========================================================
    # GROUP STANDINGS
    # =========================================================

    group_standings = {}

    if tournament.format == "hybrid":

        groups = (
            T_club_map.objects
            .filter(
                t_c_tournament=tournament,
                group_name__isnull=False
            )
            .exclude(
                group_name=""
            )
            .values_list(
                "group_name",
                flat=True
            )
            .distinct()
            .order_by(
                "group_name"
            )
        )

        for group_name in groups:

            group_teams = (
                T_club_map.objects
                .filter(
                    t_c_tournament=tournament,
                    group_name=group_name
                )
                .select_related(
                    "t_c_club"
                )
                .order_by(
                    "-points",
                    "-goals_for",
                    "goals_against",
                    "t_c_club__club_name"
                )
            )

            group_standings[group_name] = group_teams

    # =========================================================
    # ALL MATCHES
    # =========================================================

    all_matches = (
        Match.objects
        .filter(
            tournament=tournament
        )
        .select_related(
            "match_home_team",
            "match_away_team",
            "match_turf"
        )
        .order_by(
            "round_number",
            "bracket_position",
            "match_date",
            "match_time",
            "match_id"
        )
    )

    # =========================================================
    # NORMALIZE MATCH DATA
    # =========================================================

    matches_with_results = []

    for match in all_matches:

        result = (
            Result.objects
            .filter(
                result_match=match
            )
            .first()
        )

        has_home_team = match.match_home_team is not None
        has_away_team = match.match_away_team is not None

        is_bye = (
            match.match_finished
            and result is None
            and (has_home_team != has_away_team)
        )

        matches_with_results.append(
            {
                "match": match,
                "result": result,
                "is_completed": (
                    match.match_finished
                    and result is not None
                    and has_home_team
                    and has_away_team
                ),
                "is_bye": is_bye,
            }
        )

    # =========================================================
    # GROUP MATCHES
    # =========================================================

    group_matches = [
        item
        for item in matches_with_results
        if not item["match"].is_knockout
    ]

    # =========================================================
    # KNOCKOUT MATCHES
    # =========================================================

    knockout_matches = [
        item
        for item in matches_with_results
        if item["match"].is_knockout
    ]

    # =========================================================
    # PENDING SQUAD SELECTION
    # =========================================================

    my_pending_squad_matches = []
    pending_squad_matches = []

    # ---------------------------------------------------------
    # CURRENT MANAGER'S PENDING MATCHES
    # ---------------------------------------------------------

    if is_manager and my_club:

        my_matches = (
            Match.objects
            .filter(
                tournament=tournament
            )
            .filter(
                Q(match_home_team=my_club)
                |
                Q(match_away_team=my_club)
            )
            .filter(
                match_finished=False
            )
            .select_related(
                "match_home_team",
                "match_away_team"
            )
            .order_by(
                "round_number",
                "match_date",
                "match_time",
                "match_id"
            )
        )

        for match in my_matches:

            if (
                match.match_home_team == my_club
                and not match.home_squad_selected
            ):

                my_pending_squad_matches.append(
                    {
                        "match": match,
                        "side": "home",
                    }
                )

            elif (
                match.match_away_team == my_club
                and not match.away_squad_selected
            ):

                my_pending_squad_matches.append(
                    {
                        "match": match,
                        "side": "away",
                    }
                )

    # ---------------------------------------------------------
    # HOST PENDING SQUADS
    # ---------------------------------------------------------

    if (
        tournament.t_host
        and tournament.t_host.club_manager == user
    ):

        host_matches = (
            Match.objects
            .filter(
                tournament=tournament,
                match_finished=False
            )
            .select_related(
                "match_home_team",
                "match_away_team"
            )
            .order_by(
                "round_number",
                "match_date",
                "match_time",
                "match_id"
            )
        )

        for match in host_matches:

            needs_home = (
                match.match_home_team is not None
                and not match.home_squad_selected
            )

            needs_away = (
                match.match_away_team is not None
                and not match.away_squad_selected
            )

            if needs_home or needs_away:

                pending_squad_matches.append(
                    {
                        "match": match,
                        "needs_home": needs_home,
                        "needs_away": needs_away,
                    }
                )

    # =========================================================
    # MATCH COUNTS
    # =========================================================

    total_matches = len(matches_with_results)

    completed_matches = sum(
        1
        for item in matches_with_results
        if item["match"].match_finished
    )

    upcoming_matches = sum(
        1
        for item in matches_with_results
        if (
            not item["match"].match_finished
            and not item["match"].match_started
        )
    )

    live_matches = sum(
        1
        for item in matches_with_results
        if (
            item["match"].match_started
            and not item["match"].match_finished
        )
    )

    # =========================================================
    # TOURNAMENT WINNER
    # =========================================================

    tournament_winner = None

    if tournament.is_completed:

        # -----------------------------------------------------
        # ROUND ROBIN / LEAGUE
        # -----------------------------------------------------
        # A league tournament has no knockout final.
        # The champion is therefore the club ranked first in
        # the final tournament standings.
        #
        # `registrations` is already ordered by:
        #   1. points
        #   2. goals for
        #   3. goals against
        #   4. club name
        #
        # Keep the same ordering used by the Points Table so
        # the displayed champion always matches rank #1.
        # -----------------------------------------------------

        if tournament.format == "league":

            winner_registration = (
                registrations.first()
            )

            if winner_registration:
                tournament_winner = (
                    winner_registration.t_c_club
                )

        # -----------------------------------------------------
        # HYBRID / KNOCKOUT
        # -----------------------------------------------------
        # These formats have a knockout stage, so the champion
        # comes from the completed final match.
        # -----------------------------------------------------

        else:

            final_matches = [
                item["match"]
                for item in knockout_matches
                if (
                    item["match"].match_home_team
                    and
                    item["match"].match_away_team
                    and
                    item["match"].match_finished
                )
            ]

            if final_matches:

                final_match = max(
                    final_matches,
                    key=lambda m: (
                        m.round_number,
                        m.bracket_position
                    )
                )

                final_result = (
                    Result.objects
                    .filter(
                        result_match=final_match
                    )
                    .first()
                )

                if final_result:

                    if (
                        final_result.result_home_team
                        >
                        final_result.result_away_team
                    ):

                        tournament_winner = (
                            final_match.match_home_team
                        )

                    elif (
                        final_result.result_away_team
                        >
                        final_result.result_home_team
                    ):

                        tournament_winner = (
                            final_match.match_away_team
                        )

    # =========================================================
    # REGISTRATION OPEN STATUS
    # =========================================================

    today = date.today()

    registration_open = (
        not tournament.is_completed
        and not tournament.is_full
        and (
            tournament.registration_deadline is None
            or tournament.registration_deadline >= today
        )
    )

    # =========================================================
    # KNOCKOUT ROUND LABELS
    # =========================================================
    # Labels are based on the actual bracket depth, not hard-coded
    # round numbers. For 4 teams this gives Semifinal -> Final,
    # rather than incorrectly showing Round of 16.

    knockout_round_labels = {}

    if knockout_matches:

        # `knockout_matches` contains normalized dictionaries:
        # {"match": Match, "result": Result, ...}.
        # Always access the real Match through item["match"].
        round_numbers = sorted({
            item["match"].round_number
            for item in knockout_matches
        })

        round_count = len(round_numbers)

        round_names = {
            1: ["Final"],
            2: ["Semifinal", "Final"],
            3: ["Quarterfinal", "Semifinal", "Final"],
            4: ["Round of 16", "Quarterfinal", "Semifinal", "Final"],
            5: ["Round of 32", "Round of 16", "Quarterfinal", "Semifinal", "Final"],
            6: ["Round of 64", "Round of 32", "Round of 16", "Quarterfinal", "Semifinal", "Final"],
        }

        names = round_names.get(
            round_count
        )

        if names:
            for index, round_number in enumerate(round_numbers):
                knockout_round_labels[round_number] = names[index]
        else:
            for index, round_number in enumerate(round_numbers):
                if index == round_count - 1:
                    knockout_round_labels[round_number] = "Final"
                elif index == round_count - 2:
                    knockout_round_labels[round_number] = "Semifinal"
                elif index == round_count - 3:
                    knockout_round_labels[round_number] = "Quarterfinal"
                else:
                    knockout_round_labels[round_number] = f"Knockout Round {index + 1}"

    # Attach the calculated label directly to each real Match instance.
    # `knockout_matches` is a list of dictionaries, not Match objects.
    for item in knockout_matches:

        knockout_match = item["match"]
        round_number = knockout_match.round_number

        knockout_match.display_round_name = (
            knockout_round_labels.get(
                round_number,
                f"Knockout Round {round_number}"
            )
        )

    # =========================================================
    # REPAIR INVALID FUTURE KNOCKOUT BYE STATE
    # =========================================================
    # A future knockout match with only one finalist is NOT a
    # completed match.  Only first-round BYEs are real completed
    # BYEs.  This also repairs older records that were incorrectly
    # marked finished by the previous advancement logic.

    if knockout_matches:

        first_knockout_round = min(
            item["match"].round_number
            for item in knockout_matches
        )

        for item in knockout_matches:

            match = item["match"]
            has_home = match.match_home_team is not None
            has_away = match.match_away_team is not None

            if (
                match.round_number > first_knockout_round
                and match.match_finished
                and not item["result"]
                and (has_home != has_away)
            ):

                match.match_finished = False
                match.match_started = False
                match.match_finished_at = None

                match.save(
                    update_fields=[
                        "match_finished",
                        "match_started",
                        "match_finished_at",
                    ]
                )

                item["is_completed"] = False

    # =========================================================
    # MATCH CENTER GROUPS
    # =========================================================
    # The template receives already-grouped data so it never has
    # to guess whether round 2 means a Final, Round of 16, etc.
    # This keeps League, Knockout and Hybrid displays correct.

    match_center_groups = []

    if tournament.format == "league":

        match_center_groups.append({
            "stage_title": "League Stage",
            "stage_icon": "fas fa-layer-group",
            "round_name": "Round Robin",
            "matches": group_matches,
        })

    elif tournament.format == "knockout":

        for round_number in sorted(
            knockout_round_labels.keys()
        ):

            round_matches = [
                item
                for item in knockout_matches
                if item["match"].round_number == round_number
            ]

            if round_matches:
                match_center_groups.append({
                    "stage_title": "Knockout Stage",
                    "stage_icon": "fas fa-bolt",
                    "round_name": knockout_round_labels[round_number],
                    "matches": round_matches,
                })

    elif tournament.format == "hybrid":

        if group_matches:
            match_center_groups.append({
                "stage_title": "Group Stage",
                "stage_icon": "fas fa-layer-group",
                "round_name": "Round Robin",
                "matches": group_matches,
            })

        for round_number in sorted(
            knockout_round_labels.keys()
        ):

            round_matches = [
                item
                for item in knockout_matches
                if item["match"].round_number == round_number
            ]

            if round_matches:
                match_center_groups.append({
                    "stage_title": "Knockout Stage",
                    "stage_icon": "fas fa-bolt",
                    "round_name": knockout_round_labels[round_number],
                    "matches": round_matches,
                })

    # =========================================================
    # CONTEXT
    # =========================================================

    context = {

        # Tournament
        "tournament": tournament,

        # User
        "is_manager": is_manager,
        "is_registered": is_registered,
        "registration_open": registration_open,

        # Registration
        "my_registration": my_registration,
        "registration_pending_payment": (
            registration_pending_payment
        ),
        "registrations": registrations,

        # Standings
        "group_standings": group_standings,

        # Match Center
        "matches": matches_with_results,
        "group_matches": group_matches,
        "knockout_matches": knockout_matches,
        "knockout_round_labels": knockout_round_labels,
        "match_center_groups": match_center_groups,

        # User club
        "my_club": my_club,

        # Tournament statistics
        "total_matches": total_matches,
        "completed_matches": completed_matches,
        "upcoming_matches": upcoming_matches,
        "live_matches": live_matches,

        # Registration capacity
        "spots_remaining": max(
            0,
            tournament.max_teams
            -
            tournament.registered_teams_count
        ),

        # Squads
        "my_pending_squad_matches": (
            my_pending_squad_matches
        ),
        "pending_squad_matches": (
            pending_squad_matches
        ),

        # Winner
        "tournament_winner": (
            tournament_winner
        ),
    }

    # =========================================================
    # GLOBAL ROLE CONTEXT
    # =========================================================

    context.update(
        get_user_role_context(request)
    )

    # =========================================================
    # RENDER
    # =========================================================

    return render(
        request,
        "tournament/view_tournament.html",
        context
    )

@login_required_custom
def end_match(request, match_id):
    

    match = get_object_or_404(
        Match,
        match_id=match_id
    )

    user = user_acc(request)

    # A match cannot be finished before it has been started.
    if not match.match_started and not match.match_finished:
        messages.error(
            request,
            "The match must be started before it can be finished."
        )
        if match.tournament:
            return redirect(
                "view_tournament",
                t_id=match.tournament.t_id
            )
        return redirect("go_to_match", match_id=match.match_id)


    if match.match_finished:

        messages.info(
            request,
            "This match has already been finished."
        )

        if match.tournament:
            return redirect(
                "tournament_bracket",
                t_id=match.tournament.t_id
            )

        return redirect(
            "go_to_match",
            match_id=match.match_id
        )

    # TOURNAMENT MATCH

    if match.tournament:

        tournament = match.tournament

        if (
            not tournament.t_host
            or tournament.t_host.club_manager != user
        ):
            messages.error(
                request,
                "Only the tournament host can end tournament matches."
            )

            return redirect(
                "view_tournament",
                t_id=tournament.t_id
            )

    # FRIENDLY MATCH

    else:

        if (
            not match.match_home_team
            or match.match_home_team.club_manager != user
        ):
            messages.error(
                request,
                "Only the home team manager can end this match."
            )

            return redirect("club_matches")

    # GET RESULT

    try:

        result = Result.objects.get(
            result_match=match
        )

    except Result.DoesNotExist:

        messages.error(
            request,
            "Match result could not be found."
        )

        return redirect(
            "go_to_match",
            match_id=match.match_id
        )

    # STOP MATCH TIMER

    now = timezone.now()

    if match.match_started and not match.match_paused:

        if match.match_started_at:

            elapsed_since_start = int(
                (now - match.match_started_at).total_seconds()
            )

            match.match_elapsed_seconds = min(
                match.match_duration,
                match.match_elapsed_seconds + elapsed_since_start
            )

    # MARK MATCH AS FINISHED

    match.match_finished = True

    match.match_finished_at = now

    # Match can no longer be considered active.
    match.match_started = False
    match.match_paused = False
    match.match_paused_at = None

    # Make sure elapsed time never exceeds match duration.
    match.match_elapsed_seconds = min(
        match.match_elapsed_seconds,
        match.match_duration
    )

    match.save(
        update_fields=[
            "match_finished",
            "match_finished_at",
            "match_started",
            "match_paused",
            "match_paused_at",
            "match_elapsed_seconds",
        ]
    )

    # UPDATE TOURNAMENT STATISTICS

    if match.tournament:

        tournament = match.tournament

        # HOME TEAM REGISTRATION
        home_reg = None

        if match.match_home_team:

            home_reg = T_club_map.objects.filter(
                t_c_tournament=tournament,
                t_c_club=match.match_home_team
            ).first()

        # AWAY TEAM REGISTRATION
        away_reg = None

        if match.match_away_team:

            away_reg = T_club_map.objects.filter(
                t_c_tournament=tournament,
                t_c_club=match.match_away_team
            ).first()

        # UPDATE HOME TEAM STATS
        if home_reg:

            home_reg.update_stats()

        # UPDATE AWAY TEAM STATS
        if away_reg:

            away_reg.update_stats()

    # KNOCKOUT WINNER
    if match.tournament and match.is_knockout:

        try:
            advance_knockout_winner(match)
        except Exception as e:

            print(
                f"Knockout advancement error for match "
                f"{match.match_id}: {e}"
            )

    # CHECK WHETHER TOURNAMENT IS COMPLETED
    if match.tournament:

        tournament = match.tournament
        total_matches = Match.objects.filter(
            tournament=tournament
        ).count()
        finished_matches = Match.objects.filter(
            tournament=tournament,
            match_finished=True
        ).count()

        # ALL MATCHES FINISHED
        if (
            total_matches > 0
            and total_matches == finished_matches
        ):

            tournament.is_completed = True
            tournament.is_active = False

            tournament.save(
                update_fields=[
                    "is_completed",
                    "is_active",
                ]
            )

            # NOTIFY ALL REGISTERED CLUB MANAGERS
            registrations = T_club_map.objects.filter(
                t_c_tournament=tournament
            ).select_related(
                "t_c_club",
                "t_c_club__club_manager"
            )

            for reg in registrations:

                if (
                    reg.t_c_club
                    and reg.t_c_club.club_manager
                ):

                    create_notification(
                        reg.t_c_club.club_manager,
                        f"🏆 Tournament '{tournament.t_name}' "
                        f"has concluded!",
                        "success"
                    )

    # FINAL SCORE
    home_score = result.result_home_team
    away_score = result.result_away_team

    final_score_message = (
        f"{home_score} - {away_score}"
    )

    # NOTIFY HOME SQUAD
    for player in match.home_squad.all():

        if player.player_user:

            create_notification(
                player.player_user,
                f"⚽ Match ended! Final score: "
                f"{final_score_message}",
                "info"
            )

    # NOTIFY AWAY SQUAD
    for player in match.away_squad.all():

        if player.player_user:

            create_notification(
                player.player_user,
                f"⚽ Match ended! Final score: "
                f"{final_score_message}",
                "info"
            )

    # SUCCESS MESSAGE
    messages.success(
        request,
        "Match ended successfully!"
    )

    # REDIRECT
    if match.tournament:

        return redirect(
            "tournament_bracket",
            t_id=match.tournament.t_id
        )

    return redirect(
        "go_to_match",
        match_id=match.match_id
    )


@login_required_custom
def host_end_match(request, match_id):

    if request.method != "POST":

        return redirect(
            "go_to_match",
            match_id=match_id
        )

    # --------------------------------------------------------
    # GET MATCH
    # --------------------------------------------------------

    match = get_object_or_404(
        Match,
        match_id=match_id
    )

    user = user_acc(request)

    # --------------------------------------------------------
    # MUST BE TOURNAMENT MATCH
    # --------------------------------------------------------

    if not match.tournament:

        messages.error(
            request,
            "This match is not part of a tournament."
        )

        return redirect("club_matches")

    tournament = match.tournament

    # --------------------------------------------------------
    # ONLY HOST
    # --------------------------------------------------------

    if (
        not tournament.t_host
        or tournament.t_host.club_manager != user
    ):

        messages.error(
            request,
            "Only the tournament host can end tournament matches."
        )

        return redirect(
            "view_tournament",
            t_id=tournament.t_id
        )

    # --------------------------------------------------------
    # MATCH MUST HAVE STARTED
    # --------------------------------------------------------

    if not match.match_started:

        if match.match_finished:

            messages.warning(
                request,
                "Match is already finished."
            )

            return redirect(
                "tournament_bracket",
                t_id=tournament.t_id
            )

        messages.error(
            request,
            "Match has not started yet."
        )

        return redirect(
            "go_to_match",
            match_id=match.match_id
        )

    # --------------------------------------------------------
    # ALREADY FINISHED
    # --------------------------------------------------------

    if match.match_finished:

        messages.warning(
            request,
            "Match is already finished."
        )

        return redirect(
            "tournament_bracket",
            t_id=tournament.t_id
        )

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    try:

        result = Result.objects.get(
            result_match=match
        )

    except Result.DoesNotExist:

        messages.error(
            request,
            "Match result could not be found."
        )

        return redirect(
            "go_to_match",
            match_id=match.match_id
        )

    # --------------------------------------------------------
    # TIMER
    # --------------------------------------------------------

    now = timezone.now()

    if (
        match.match_started_at
        and not match.match_paused
    ):

        elapsed_since_start = int(
            (
                now
                -
                match.match_started_at
            ).total_seconds()
        )

        match.match_elapsed_seconds = min(
            match.match_duration,
            (
                match.match_elapsed_seconds
                +
                elapsed_since_start
            )
        )

    # --------------------------------------------------------
    # FINISH MATCH
    # --------------------------------------------------------

    match.match_finished = True
    match.match_finished_at = now

    match.match_started = False

    match.match_paused = False
    match.match_paused_at = None

    match.match_elapsed_seconds = min(
        match.match_elapsed_seconds,
        match.match_duration
    )

    match.save(
        update_fields=[
            "match_finished",
            "match_finished_at",
            "match_started",
            "match_paused",
            "match_paused_at",
            "match_elapsed_seconds",
        ]
    )

    # --------------------------------------------------------
    # UPDATE GROUP / CLUB STATS
    # --------------------------------------------------------

    home_reg = None
    away_reg = None

    if match.match_home_team:

        home_reg = T_club_map.objects.filter(
            t_c_tournament=tournament,
            t_c_club=match.match_home_team
        ).first()

    if match.match_away_team:

        away_reg = T_club_map.objects.filter(
            t_c_tournament=tournament,
            t_c_club=match.match_away_team
        ).first()

    if home_reg:
        home_reg.update_stats()

    if away_reg:
        away_reg.update_stats()

    # --------------------------------------------------------
    # KNOCKOUT WINNER
    # --------------------------------------------------------

    if match.is_knockout:

        try:

            advance_knockout_winner(
                match
            )

        except Exception as exc:

            print(
                "Knockout advancement error "
                f"for match {match.match_id}: {exc}"
            )

    # --------------------------------------------------------
    # HYBRID:
    # AFTER A GROUP MATCH FINISHES,
    # CHECK WHETHER THE ENTIRE GROUP STAGE IS COMPLETE.
    #
    # If yes, create the knockout bracket.
    # --------------------------------------------------------

    if (
        tournament.format == "hybrid"
        and not match.is_knockout
    ):

        try:

            populate_hybrid_knockout(
                tournament
            )

        except Exception as exc:

            print(
                "Hybrid knockout creation error "
                f"for tournament {tournament.t_id}: {exc}"
            )

    # --------------------------------------------------------
    # NOTIFICATIONS
    # --------------------------------------------------------

    final_score_message = (
        f"{result.result_home_team} - "
        f"{result.result_away_team}"
    )

    for player in match.home_squad.all():

        if player.player_user:

            create_notification(
                player.player_user,
                f"⚽ Match ended! "
                f"Final score: "
                f"{final_score_message}",
                "info"
            )

    for player in match.away_squad.all():

        if player.player_user:

            create_notification(
                player.player_user,
                f"⚽ Match ended! "
                f"Final score: "
                f"{final_score_message}",
                "info"
            )

    # --------------------------------------------------------
    # CHECK TOURNAMENT COMPLETION
    # --------------------------------------------------------

    total_matches = Match.objects.filter(
        tournament=tournament
    ).count()

    finished_matches = Match.objects.filter(
        tournament=tournament,
        match_finished=True
    ).count()

    # --------------------------------------------------------
    # AUTO COMPLETE
    # --------------------------------------------------------

    if (
        total_matches > 0
        and total_matches == finished_matches
    ):

        tournament.is_completed = True
        tournament.is_active = False

        tournament.save(
            update_fields=[
                "is_completed",
                "is_active",
            ]
        )

        registrations = (
            T_club_map.objects
            .filter(
                t_c_tournament=tournament
            )
            .select_related(
                "t_c_club",
                "t_c_club__club_manager"
            )
        )

        for registration in registrations:

            if (
                registration.t_c_club
                and
                registration.t_c_club.club_manager
            ):

                create_notification(
                    registration.t_c_club.club_manager,
                    f"🏆 Tournament "
                    f"'{tournament.t_name}' "
                    f"has concluded!",
                    "success"
                )

    # --------------------------------------------------------
    # SUCCESS MESSAGE
    # --------------------------------------------------------

    home_name = (
        match.match_home_team.club_name
        if match.match_home_team
        else "TBD"
    )

    away_name = (
        match.match_away_team.club_name
        if match.match_away_team
        else "TBD"
    )

    if match.is_knockout:

        messages.success(
            request,
            f"Match finished! "
            f"{home_name} "
            f"{result.result_home_team} - "
            f"{result.result_away_team} "
            f"{away_name}. "
            f"Winner advanced to the next round!"
        )

    else:

        messages.success(
            request,
            f"Match finished! "
            f"{home_name} "
            f"{result.result_home_team} - "
            f"{result.result_away_team} "
            f"{away_name}"
        )

    return redirect(
        "tournament_bracket",
        t_id=tournament.t_id
    )

@login_required_custom
def tournament_bracket(request, t_id):
    """
    Display the complete tournament results.

    Displays:
        1. Round Robin / Group Stage matches
        2. Knockout rounds
        3. Final
        4. Tournament champion

    Rules:
        - Only matches belonging to this tournament are displayed.
        - Friendly matches are never included.
        - Round-robin/group-stage matches are is_knockout=False.
        - Knockout matches are is_knockout=True.
        - BYE matches never display a score.
        - TBD matches never display a score.
        - Tournament winner is calculated from the completed final.
    """

    tournament = get_object_or_404(
        Tournament,
        t_id=t_id
    )

    user = user_acc(request)

    # ---------------------------------------------------------
    # HOST
    # ---------------------------------------------------------

    is_host = (
        tournament.t_host
        and tournament.t_host.club_manager == user
    )

    tournament_matches = (
        Match.objects
        .filter(
            tournament=tournament
        )
        .select_related(
            "match_home_team",
            "match_away_team"
        )
        .order_by(
            "round_number",
            "match_date",
            "match_time",
            "match_id"
        )
    )


    league_matches = [
        match
        for match in tournament_matches
        if not match.is_knockout
    ]

    # ---------------------------------------------------------
    # BUILD ROUND ROBIN RESULT LIST
    # ---------------------------------------------------------

    round_robin_matches = []

    for match in league_matches:

        has_home_team = (
            match.match_home_team is not None
        )

        has_away_team = (
            match.match_away_team is not None
        )

        is_real_match = (
            has_home_team
            and has_away_team
        )

        result = None

        if is_real_match:

            result = (
                Result.objects
                .filter(
                    result_match=match
                )
                .first()
            )

        home_score = None
        away_score = None

        if result and is_real_match:

            home_score = result.result_home_team
            away_score = result.result_away_team

        round_robin_matches.append({

            "match": match,

            "result": result,

            "home_score": home_score,

            "away_score": away_score,

            "is_real_match": is_real_match,

            "has_home_team": has_home_team,

            "has_away_team": has_away_team,

        })

    group_stage_matches = []

    if tournament.format == "hybrid":

        group_stage_matches = round_robin_matches

    # ---------------------------------------------------------
    # KNOCKOUT MATCHES
    # ---------------------------------------------------------

    knockout_matches = (
        Match.objects
        .filter(
            tournament=tournament,
            is_knockout=True
        )
        .select_related(
            "match_home_team",
            "match_away_team"
        )
        .order_by(
            "round_number",
            "bracket_position",
            "match_id"
        )
    )

    # ---------------------------------------------------------
    # BUILD KNOCKOUT BRACKET
    # ---------------------------------------------------------

    bracket = {}

    for match in knockout_matches:

        round_num = match.round_number

        if round_num not in bracket:

            bracket[round_num] = []

        # -----------------------------------------------------
        # TEAMS
        # -----------------------------------------------------

        has_home_team = (
            match.match_home_team is not None
        )

        has_away_team = (
            match.match_away_team is not None
        )

        is_real_match = (
            has_home_team
            and has_away_team
        )

        # -----------------------------------------------------
        # BYE
        # -----------------------------------------------------

        is_bye = (
            match.match_finished
            and (
                (
                    has_home_team
                    and not has_away_team
                )
                or
                (
                    not has_home_team
                    and has_away_team
                )
            )
        )

        result = None

        if is_real_match and not is_bye:

            result = (
                Result.objects
                .filter(
                    result_match=match
                )
                .first()
            )

        # -----------------------------------------------------
        # SCORES
        # -----------------------------------------------------

        home_score = None
        away_score = None

        if result and is_real_match and not is_bye:

            home_score = result.result_home_team
            away_score = result.result_away_team

        # -----------------------------------------------------
        # ADD MATCH
        # -----------------------------------------------------

        bracket[round_num].append({

            "match": match,

            "result": result,

            "home_score": home_score,

            "away_score": away_score,

            "is_bye": is_bye,

            "is_real_match": is_real_match,

            "has_home_team": has_home_team,

            "has_away_team": has_away_team,

        })

    bracket_rounds = []

    for round_num in sorted(bracket.keys()):

        matches = bracket[round_num]

        highest_round = max(
            bracket.keys()
        ) if bracket else None

        if round_num == highest_round:

            round_name = "Final"

        elif len(bracket) == 2:

            # Two knockout rounds:
            # Round 1 = Semi Final
            # Round 2 = Final

            if round_num == sorted(bracket.keys())[0]:

                round_name = "Semi Final"

            else:

                round_name = "Final"

        elif len(bracket) == 3:

            round_positions = sorted(
                bracket.keys()
            )

            if round_num == round_positions[0]:

                round_name = "Quarter Final"

            elif round_num == round_positions[1]:

                round_name = "Semi Final"

            else:

                round_name = "Final"

        else:

            round_name = f"Round {round_num}"

        bracket_rounds.append({

            "round_num": round_num,

            "round_name": round_name,

            "matches": matches,

        })

    final_match = None
    final_result = None
    tournament_winner = None

    if bracket:

        final_round_number = max(
            bracket.keys()
        )

        final_candidates = bracket.get(
            final_round_number,
            []
        )

        # Usually there is one final match.
        # Prefer a real completed match.
        for item in final_candidates:

            if (
                item["is_real_match"]
                and item["match"].match_finished
                and item["result"]
            ):

                final_match = item["match"]
                final_result = item["result"]

                break

        # Fallback: if the final exists but isn't finished,
        # keep the actual final match available.
        if final_match is None and final_candidates:

            for item in final_candidates:

                if item["is_real_match"]:

                    final_match = item["match"]
                    final_result = item["result"]

                    break

    if (
        final_match
        and final_result
        and final_match.match_finished
        and final_match.match_home_team
        and final_match.match_away_team
    ):

        home_score = final_result.result_home_team
        away_score = final_result.result_away_team

        if home_score > away_score:

            tournament_winner = (
                final_match.match_home_team
            )

        elif away_score > home_score:

            tournament_winner = (
                final_match.match_away_team
            )

    # ---------------------------------------------------------
    # CONTEXT
    # ---------------------------------------------------------

    context = {

        "tournament": tournament,

        "is_host": is_host,

        # Round Robin
        "round_robin_matches": (
            round_robin_matches
            if tournament.format == "league"
            else []
        ),

        # Group Stage
        "group_stage_matches": (
            group_stage_matches
        ),

        # Knockout
        "bracket_rounds": bracket_rounds,

        # Final
        "final_match": final_match,

        "final_result": final_result,

        # Winner
        "tournament_winner": tournament_winner,

    }

    context.update(
        get_user_role_context(request)
    )

    return render(
        request,
        "tournament/bracket.html",
        context
    )


@club_manager_required
def select_squad(request, match_id, side):
    """
    Select squad - Each manager selects ONLY their own team's squad.

    TOURNAMENT MATCHES:
      - Each club manager selects their OWN squad (home or away)
      - Host selects only their own squad, not opponent's
      - Squad size is taken from tournament configuration

    FRIENDLY MATCHES:
      - Home manager selects home squad when creating match
      - Away manager selects away squad when fixing match
      - Each manager controls only their own team
    """
    match = get_object_or_404(Match, match_id=match_id)
    user = user_acc(request)

    # Determine squad size
    if match.tournament:
        squad_size = match.tournament.squad_size
    else:
        squad_size = match.squad_size

    # Determine which club we are selecting for
    if side == "home":
        club = match.match_home_team
    else:
        club = match.match_away_team

    # SECURITY: Verify user is the manager of THIS club
    if not club or club.club_manager != user:
        messages.error(request, "You can only select your own team squad.")
        if match.tournament:
            return redirect("view_tournament", t_id=match.tournament.t_id)
        return redirect("club_matches")

    # Additional check: For tournament matches, verify match belongs to tournament
    if match.tournament:
        # Verify this club is actually in this tournament match
        if side == "home" and match.match_home_team != club:
            messages.error(request, "Your club is not the home team in this match.")
            return redirect("view_tournament", t_id=match.tournament.t_id)
        if side == "away" and match.match_away_team != club:
            messages.error(request, "Your club is not the away team in this match.")
            return redirect("view_tournament", t_id=match.tournament.t_id)

    players = Player.objects.filter(player_club=club)

    if players.count() == 0:
        messages.warning(request, f"{club.club_name} has no registered players. Please add players first.")
        if match.tournament:
            return redirect("view_tournament", t_id=match.tournament.t_id)
        return redirect("club_matches")

    if request.method == "POST":
        starters, subs = [], []

        for player in players:
            role = request.POST.get(f"role_{player.player_id}")
            if role == "starter":
                starters.append(player.player_id)
            elif role == "sub":
                subs.append(player.player_id)

        # Validate starter count matches squad_size
        if len(starters) != squad_size:
            messages.error(request, f"You must select exactly {squad_size} starters. You selected {len(starters)}.")
        else:
            starter_objs = Player.objects.filter(player_id__in=starters)
            sub_objs = Player.objects.filter(player_id__in=subs)

            if side == "home":
                match.home_squad.set(starter_objs)
                match.home_subs.set(sub_objs)
                match.home_squad_selected = True
            else:
                match.away_squad.set(starter_objs)
                match.away_subs.set(sub_objs)
                match.away_squad_selected = True

            match.save()
            messages.success(request, f"{side.title()} squad selected! {squad_size} starters + {len(subs)} subs.")

            for player in starter_objs:
                create_notification(
                    player.player_user,
                    f"You have been selected as a starter for the match on {match.match_date} at {match.match_time}.",
                    'success'
                )
            for player in sub_objs:
                create_notification(
                    player.player_user,
                    f"You have been selected as a substitute for the match on {match.match_date} at {match.match_time}.",
                    'info'
                )

            # Tournament logic: redirect back to tournament view
            if match.tournament:
                return redirect("view_tournament", t_id=match.tournament.t_id)
            else:
                return redirect("go_to_match", match_id=match.match_id)

    context = {
        "match": match,
        "players": players,
        "side": side,
        "squad_size": squad_size,
        "is_tournament": bool(match.tournament),
        "club_name": club.club_name,
    }
    context.update(get_user_role_context(request))

    return render(request, "user/select_squad.html", context)


@login_required_custom
def go_to_match(request, match_id):
    """
    Go to match page - handles both friendly and tournament matches.

    Tournament matches:
        - Each manager controls their own team for squad selection.
        - Tournament host can record actions for BOTH teams.
        - Tournament host can update final scores.
        - Match timer state is provided to the template.
    """

    match = get_object_or_404(
        Match,
        match_id=match_id
    )

    home_team = match.match_home_team
    away_team = match.match_away_team

    current_user = user_acc(request)

    # AWAY TEAM MUST EXIST
    if not away_team:

        if match.tournament:

            return redirect(
                "view_tournament",
                t_id=match.tournament.t_id
            )

        return redirect("club_matches")

    # GET / CREATE RESULT
    result, created = Result.objects.get_or_create(
        result_match=match
    )

    # IMPORTANT:
    # Tournament squads are NEVER auto-assigned here.
    # Each home/away manager must explicitly complete squad selection.
    # This prevents simply opening a match from making a team "ready".

    # PLAYERS
    home_players = (
        list(match.home_squad.all())
        +
        list(match.home_subs.all())
    )

    away_players = (
        list(match.away_squad.all())
        +
        list(match.away_subs.all())
    )

    # MATCH ACHIEVEMENTS / EVENTS
    goals = Goal.objects.filter(
        result=result
    )

    assists = Assist.objects.filter(
        result=result
    )

    saves = Save.objects.filter(
        result=result
    )

    # Achievement types
    for goal in goals:
        goal.achievement_type = "goal"

    for assist in assists:
        assist.achievement_type = "assist"

    for save in saves:
        save.achievement_type = "save"

    # Combine + newest first
    achievements = sorted(
        chain(
            goals,
            assists,
            saves
        ),
        key=attrgetter("time"),
        reverse=True
    )

    # USER PERMISSIONS
    is_home_manager = (
        home_team
        and home_team.club_manager == current_user
    )

    is_away_manager = (
        away_team
        and away_team.club_manager == current_user
    )

    # TOURNAMENT HOST
    is_tournament_host = False

    if (
        match.tournament
        and match.tournament.t_host
    ):

        is_tournament_host = (
            match.tournament.t_host.club_manager
            == current_user
        )

    # RECORDING PERMISSIONS
    can_record_home = (
        is_home_manager
        or is_tournament_host
    )

    can_record_away = (
        is_away_manager
        or is_tournament_host
    )

    # SQUAD SIZE
    if match.tournament:
        squad_size = match.tournament.squad_size

    else:
        squad_size = match.squad_size

    # TIMER STATE

    elapsed_seconds = match.match_elapsed_seconds or 0
    match_duration = match.match_duration or 5400

    if (
        match.match_started
        and not match.match_finished
        and not match.match_paused
        and match.match_started_at
    ):

        current_elapsed = int(
            (
                timezone.now()
                -
                match.match_started_at
            ).total_seconds()
        )

        elapsed_seconds = min(
            match_duration,
            elapsed_seconds + current_elapsed
        )

    # Never allow elapsed time to exceed duration.
    elapsed_seconds = min(
        elapsed_seconds,
        match_duration
    )

    # TIMER STATUS
    if match.match_finished:

        timer_status = "finished"

    elif match.match_paused:
        timer_status = "paused"
    elif match.match_started:
        timer_status = "running"
    else:
        timer_status = "not_started"


    context = {
        "match": match,
        "result": result,
        "home_team": home_team,
        "away_team": away_team,
        "home_players": home_players,
        "away_players": away_players,
        "achievements": achievements,
        "is_home_manager": is_home_manager,
        "is_away_manager": is_away_manager,
        "can_record_home": can_record_home,
        "can_record_away": can_record_away,
        "is_tournament_host": is_tournament_host,
        "squad_size": squad_size,
        "home_squad_selected": match.home_squad_selected,
        "away_squad_selected": match.away_squad_selected,
        "match_duration": match_duration,
        "elapsed_seconds": elapsed_seconds,
        "match_elapsed_seconds": match.match_elapsed_seconds,
        "match_started": match.match_started,
        "match_started_at": match.match_started_at,
        "match_paused": match.match_paused,
        "match_paused_at": match.match_paused_at,
        "match_finished": match.match_finished,
        "match_finished_at": match.match_finished_at,
        "timer_status": timer_status,
        "can_start_match": (
            not match.match_started
            and not match.match_finished
            and bool(match.match_home_team)
            and bool(match.match_away_team)
            and bool(match.home_squad_selected)
            and bool(match.away_squad_selected)
            and match.home_squad.exists()
            and match.away_squad.exists()
        ),
        "both_squads_ready": (
            bool(match.home_squad_selected)
            and bool(match.away_squad_selected)
            and match.home_squad.exists()
            and match.away_squad.exists()
        ),
        "start_block_reason": (
            "Home team squad is pending."
            if not match.home_squad_selected
            else "Away team squad is pending."
            if not match.away_squad_selected
            else "Home and away squads must contain selected players."
            if not match.home_squad.exists() or not match.away_squad.exists()
            else ""
        ),
        "match_is_live": (
            match.match_started
            and not match.match_finished
        ),
        "match_is_finished": match.match_finished,
        "match_is_paused": match.match_paused,
    }

    context.update(
        get_user_role_context(request)
    )
    return render(
        request,
        "club/go_to_match.html",
        context
    )


@club_manager_required
def generate_tournament_fixtures(request, t_id):
    """
    Generate tournament fixtures.

    Hybrid tournaments:
        Group fixtures are generated now.
        Knockout fixtures are generated later, after the
        entire group stage is complete.
    """

    tournament = get_object_or_404(
        Tournament,
        t_id=t_id
    )

    user = user_acc(request)

    # --------------------------------------------------------
    # ONLY HOST
    # --------------------------------------------------------

    if (
        not tournament.t_host
        or tournament.t_host.club_manager != user
    ):

        messages.error(
            request,
            "Only the tournament host can generate fixtures."
        )

        return redirect(
            "view_tournament",
            t_id=t_id
        )

    # --------------------------------------------------------
    # PREVENT DUPLICATE GENERATION
    # --------------------------------------------------------

    if Match.objects.filter(
        tournament=tournament
    ).exists():

        messages.warning(
            request,
            "Fixtures have already been generated."
        )

        return redirect(
            "view_tournament",
            t_id=t_id
        )

    # --------------------------------------------------------
    # PAID REGISTRATIONS
    # --------------------------------------------------------

    registrations = (
        T_club_map.objects
        .filter(
            t_c_tournament=tournament,
            is_paid=True
        )
        .select_related("t_c_club")
    )

    clubs = [
        registration.t_c_club
        for registration in registrations
        if registration.t_c_club
    ]

    number_of_clubs = len(clubs)

    # --------------------------------------------------------
    # MINIMUM TEAMS
    # --------------------------------------------------------

    if number_of_clubs < 4:

        messages.error(
            request,
            "Need at least 4 registered teams to generate fixtures."
        )

        return redirect(
            "view_tournament",
            t_id=t_id
        )

    # --------------------------------------------------------
    # GENERATE
    # --------------------------------------------------------

    try:

        if tournament.format == "league":

            _generate_round_robin(
                tournament,
                clubs
            )

        elif tournament.format == "knockout":

            _generate_knockout(
                tournament,
                clubs
            )

        elif tournament.format == "hybrid":

            _generate_hybrid(
                tournament,
                clubs,
                tournament.teams_per_group,
                tournament.teams_qualifying
            )

        else:

            messages.error(
                request,
                "Invalid tournament format."
            )

            return redirect(
                "view_tournament",
                t_id=t_id
            )

    except ValueError as exc:

        messages.error(
            request,
            str(exc)
        )

        return redirect(
            "view_tournament",
            t_id=t_id
        )

    # --------------------------------------------------------
    # ENSURE SQUAD SIZE
    # --------------------------------------------------------

    Match.objects.filter(
        tournament=tournament
    ).update(
        squad_size=tournament.squad_size
    )

    # --------------------------------------------------------
    # NOTIFY CLUB MANAGERS
    # --------------------------------------------------------

    matches = Match.objects.filter(
        tournament=tournament
    )

    notified_clubs = set()

    for match in matches:

        # HOME
        if (
            match.match_home_team
            and match.match_home_team.club_manager
        ):

            home_manager = (
                match.match_home_team.club_manager
            )

            club_id = (
                match.match_home_team.club_id
            )

            if club_id not in notified_clubs:

                create_notification(
                    home_manager,
                    f"Fixtures generated for "
                    f"'{tournament.t_name}'! "
                    f"Please select your squad.",
                    "info"
                )

                notified_clubs.add(
                    club_id
                )

        # AWAY
        if (
            match.match_away_team
            and match.match_away_team.club_manager
        ):

            away_manager = (
                match.match_away_team.club_manager
            )

            club_id = (
                match.match_away_team.club_id
            )

            if club_id not in notified_clubs:

                create_notification(
                    away_manager,
                    f"Fixtures generated for "
                    f"'{tournament.t_name}'! "
                    f"Please select your squad.",
                    "info"
                )

                notified_clubs.add(
                    club_id
                )

    # --------------------------------------------------------
    # --------------------------------------------------------
    # EXPLICIT SQUAD SELECTION ONLY
    # --------------------------------------------------------
    # Do NOT auto-assign squads here.
    # Every club manager must explicitly select the squad for each
    # tournament match before that match can be started.

    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    if tournament.format == "hybrid":

        messages.success(
            request,
            f"Group-stage fixtures generated "
            f"for {number_of_clubs} teams. "
            f"Knockout stage will appear after "
            f"all group matches are finished."
        )

    else:

        messages.success(
            request,
            f"Fixtures generated for "
            f"{number_of_clubs} teams!"
        )

    if auto_assigned:

        messages.info(
            request,
            "Auto-assigned squads for: "
            + ", ".join(auto_assigned)
        )

    return redirect(
        "view_tournament",
        t_id=t_id
    )


@club_manager_required
@login_required_custom
def host_update_score(request, match_id):
    """Update a tournament score without ever implicitly starting a match."""

    if request.method != "POST":
        return redirect("go_to_match", match_id=match_id)

    match = get_object_or_404(Match, match_id=match_id)
    user = user_acc(request)

    if not match.tournament:
        messages.error(request, "This match is not part of a tournament.")
        return redirect("club_matches")

    tournament = match.tournament

    if (
        not tournament.t_host
        or tournament.t_host.club_manager != user
    ):
        messages.error(
            request,
            "Only the tournament host can update scores."
        )
        return redirect(
            "view_tournament",
            t_id=tournament.t_id
        )

    # A score can only be changed for a match that has actually started.
    if not match.match_started or match.match_finished:
        messages.error(
            request,
            "The match must be started and live before the score can be updated."
        )
        return redirect("go_to_match", match_id=match_id)

    # Both squads must have been explicitly selected.
    if not match.home_squad_selected or not match.away_squad_selected:
        messages.error(
            request,
            "Both teams must select their squads before the score can be updated."
        )
        return redirect("go_to_match", match_id=match_id)

    try:
        home_score = int(request.POST.get("home_score", 0))
        away_score = int(request.POST.get("away_score", 0))
    except (TypeError, ValueError):
        messages.error(request, "Invalid score values.")
        return redirect("go_to_match", match_id=match_id)

    if home_score < 0 or away_score < 0:
        messages.error(request, "Scores cannot be negative.")
        return redirect("go_to_match", match_id=match_id)

    result, created = Result.objects.get_or_create(
        result_match=match
    )

    result.result_home_team = home_score
    result.result_away_team = away_score
    result.save()

    messages.success(
        request,
        f"Score updated: {match.match_home_team.club_name} "
        f"{home_score} - {away_score} "
        f"{match.match_away_team.club_name}"
    )

    return redirect("go_to_match", match_id=match_id)


@club_manager_required
def host_record_action(request, match_id):
    """
    Tournament host records player actions (goal, assist, save) for EITHER team.
    This bypasses the home/away manager restrictions for tournament matches.
    """
    if request.method != "POST":
        return redirect("go_to_match", match_id=match_id)

    match = get_object_or_404(Match, match_id=match_id)
    user = user_acc(request)

    # Only tournament host can use this
    if not match.tournament or match.tournament.t_host.club_manager != user:
        messages.error(request, "Only the tournament host can record actions for tournament matches.")
        return redirect("go_to_match", match_id=match_id)

    # Match must be live
    if not match.match_started or match.match_finished:
        messages.error(request, "Match must be live to record actions.")
        return redirect("go_to_match", match_id=match_id)

    action = request.POST.get("action")
    player_id = request.POST.get("player_id")
    team_side = request.POST.get("team_side")  # 'home' or 'away'

    if not player_id or not action or not team_side:
        messages.error(request, "Missing required data.")
        return redirect("go_to_match", match_id=match_id)

    player = get_object_or_404(Player, player_id=player_id)
    result = get_object_or_404(Result, result_match=match)

    # Determine which club this action is for
    if team_side == "home":
        for_club = match.match_home_team
    else:
        for_club = match.match_away_team

    # Validate player belongs to the correct team
    if player.player_club != for_club:
        messages.error(request, "Player does not belong to the selected team.")
        return redirect("go_to_match", match_id=match_id)

    # Record the action
    if action == "goal":
        table = Goal()
        if team_side == "home":
            result.result_home_team += 1
        else:
            result.result_away_team += 1
        notif_msg = f"GOAL! {player.player_card_name} scored for {for_club.club_name}!"
        notif_type = 'success'
    elif action == "assist":
        table = Assist()
        notif_msg = f"ASSIST! {player.player_card_name} provided an assist for {for_club.club_name}!"
        notif_type = 'info'
    elif action == "save":
        table = Save()
        notif_msg = f"SAVE! {player.player_card_name} made a crucial save for {for_club.club_name}!"
        notif_type = 'info'
    else:
        messages.warning(request, "Invalid action selected.")
        return redirect("go_to_match", match_id=match_id)

    table.player = player
    table.result = result
    table.for_club = for_club
    table.save()
    result.save()

    # Update player rating
    player.player_rating = calculate_player_rating(player)
    player.save()

    # Notify all players
    for p in match.home_squad.all():
        create_notification(p.player_user, notif_msg, notif_type)
    for p in match.away_squad.all():
        create_notification(p.player_user, notif_msg, notif_type)

    messages.success(request, notif_msg)
    return redirect("go_to_match", match_id=match_id)