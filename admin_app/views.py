from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.db.models import Count, Q, Exists, OuterRef, Sum, Prefetch, Subquery
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from itertools import chain
from operator import attrgetter
import re
from datetime import date, datetime, time as dt_time

from visitor_app.models import User
from user_app.models import (
    Player, Club, Turf, Match, Tournament, T_club_map,
    Position, Result, Goal, Assist, Save, Time_Schedule,
    Turf_time_map, Notification, Booking, Payment,TournamentPayment,
)


def _admin_required(request):
    """Check if user is admin (superuser) or has admin session."""
    if request.session.get("admin_id"):
        return True
    if request.user.is_authenticated and request.user.is_superuser:
        request.session["admin_id"] = request.user.id
        return True
    return False

def _attach_match_result(match):
   
    try:
        result = Result.objects.prefetch_related(
            'goal_set__player', 'goal_set__for_club',
            'assist_set__player', 'assist_set__for_club',
            'save_set__player', 'save_set__for_club'
        ).get(result_match=match)
        
        match.result = result
        match.goals = result.goal_set.all()
        match.assists = result.assist_set.all()
        match.saves = result.save_set.all()
    except Result.DoesNotExist:
        match.result = None
        match.goals = []
        match.assists = []
        match.saves = []


def admin_home(request):
    if not _admin_required(request):
        return redirect("admin_login")

    visitor_subquery_club = Club.objects.filter(club_manager_id=OuterRef("pk"))
    visitor_subquery_player = Player.objects.filter(player_user_id=OuterRef("pk"))
    visitor_subquery_turf = Turf.objects.filter(turf_owner_id=OuterRef("pk"))

    # Revenue stats — convert paise to rupees
    total_revenue = (Payment.objects.filter(payment_status="Success").aggregate(
        total=Sum("amount")
    )["total"] or 0) // 100

    # Booking stats
    booking_stats = {
        "pending": Booking.objects.filter(status="Pending").count(),
        "accepted": Booking.objects.filter(status="Accepted").count(),
        "rejected": Booking.objects.filter(status="Rejected").count(),
        "paid": Booking.objects.filter(is_paid=True).count(),
    }

    # Recent notifications
    recent_notifications = Notification.objects.select_related("user").order_by(
        "-created_at"
    )[:5]

    context = {
        "total_players": Player.objects.count(),
        "total_clubs": Club.objects.count(),
        "total_turfs": Turf.objects.count(),
        "total_matches": Match.objects.count(),
        "total_tournaments": Tournament.objects.count(),
        "total_users": User.objects.count(),
        "total_visitors": User.objects.filter(
            ~Exists(visitor_subquery_club),
            ~Exists(visitor_subquery_player),
            ~Exists(visitor_subquery_turf),
        ).count(),
        "total_club_managers": User.objects.filter(
            Exists(visitor_subquery_club)
        ).count(),
        "total_turf_owners": User.objects.filter(
            Exists(visitor_subquery_turf)
        ).count(),
        "total_revenue": total_revenue,
        "booking_stats": booking_stats,
        "recent_notifications": recent_notifications,
        "unread_notifications": Notification.objects.filter(is_read=False).count(),
    }
    return render(request, "admin/admin_home.html", context)

def admin_login(request):
    if _admin_required(request):
        return redirect("admin_home")
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_superuser:
            login(request, user)
            request.session["admin_id"] = user.id
            messages.success(request, f"Welcome back, {user.username}!")
            return redirect("admin_home")
        messages.error(
            request,
            "Invalid admin credentials. Use superuser username and password.",
        )
    return render(request, "admin/admin_login.html")


def admin_logout(request):
    logout(request)
    request.session.flush()
    messages.success(request, "You have been logged out successfully.")
    return redirect("admin_login")

def admin_view_normal_users(request):
    if not _admin_required(request):
        return redirect("admin_login")

    users = User.objects.all()
    role_filter = request.GET.get("role", "all")

    club_subquery = Club.objects.filter(club_manager=OuterRef("pk"))
    player_subquery = Player.objects.filter(player_user=OuterRef("pk"))
    turf_subquery = Turf.objects.filter(turf_owner=OuterRef("pk"))

    users = users.annotate(
        has_club=Exists(club_subquery),
        has_player=Exists(player_subquery),
        has_turf=Exists(turf_subquery),
    )

    if role_filter == "player":
        users = users.filter(has_player=True)
    elif role_filter == "club_manager":
        users = users.filter(has_club=True)
    elif role_filter == "turf_owner":
        users = users.filter(has_turf=True)
    elif role_filter == "visitor":
        users = users.filter(has_club=False, has_player=False, has_turf=False)

    user_list = []
    for u in users:
        u.is_player = u.has_player
        u.is_club_manager = u.has_club
        u.is_turf_owner = u.has_turf
        user_list.append(u)

    return render(request, "admin/admin_view_normal_users.html", {
        "users": user_list,
        "role_filter": role_filter,
    })

def admin_view_players(request):
    if not _admin_required(request):
        return redirect("admin_login")

    players = Player.objects.select_related(
        "player_user", "player_position", "player_club"
    ).annotate(
        total_goals=Count("goal", distinct=True),
        total_assists=Count("assist", distinct=True),
        total_saves=Count("save", distinct=True),
    )

    positions = Position.objects.all()

    name = request.GET.get("name")
    gender = request.GET.get("gender")
    district = request.GET.get("district")
    position = request.GET.get("position")
    club = request.GET.get("club")
    sort = request.GET.get("sort")

    if name:
        players = players.filter(player_card_name__icontains=name)
    if gender:
        players = players.filter(player_user__user_gender__iexact=gender)
    if district:
        players = players.filter(player_district__icontains=district)
    if position:
        players = players.filter(player_position__position_code=position)
    if club:
        players = players.filter(player_club__club_name__icontains=club)
    if sort == "high":
        players = players.order_by("-player_rating")
    elif sort == "low":
        players = players.order_by("player_rating")
    else:
        players = players.order_by("-player_id")

    return render(request, "admin/admin_view_players.html", {
        "players": players,
        "positions": positions,
    })


def admin_delete_player(request, player_id):
    if not _admin_required(request):
        return redirect("admin_login")
    player = get_object_or_404(Player, player_id=player_id)
    if request.method == "POST":
        name = player.player_card_name
        player.delete()
        messages.success(request, f"Player '{name}' deleted successfully.")
    return redirect("admin_view_players")


def admin_view_clubs(request):
    if not _admin_required(request):
        return redirect("admin_login")

    clubs = Club.objects.select_related("club_manager").annotate(
        player_count=Count("player", distinct=True)
    )

    name = request.GET.get("name")
    district = request.GET.get("district")
    manager = request.GET.get("manager")
    sort = request.GET.get("sort")

    if name:
        clubs = clubs.filter(club_name__icontains=name)
    if district:
        clubs = clubs.filter(club_district__icontains=district)
    if manager:
        clubs = clubs.filter(
            Q(club_manager__user_name__icontains=manager)
            | Q(club_manager__user_email__icontains=manager)
        )
    if sort == "high":
        clubs = clubs.order_by("-club_weight")
    elif sort == "low":
        clubs = clubs.order_by("club_weight")
    else:
        clubs = clubs.order_by("-club_id")

    return render(request, "admin/admin_view_clubs.html", {"clubs": clubs})


def validate_club(request, club_id):
    if not _admin_required(request):
        return redirect("admin_login")
    club = get_object_or_404(Club, club_id=club_id)
    if request.method == "POST":
        club.is_validated = True
        club.validated_at = timezone.now()
        club.save()
        messages.success(request, f"Club '{club.club_name}' validated successfully.")
    return redirect("admin_view_clubs")


def admin_delete_club(request, club_id):
    if not _admin_required(request):
        return redirect("admin_login")
    club = get_object_or_404(Club, club_id=club_id)
    if request.method == "POST":
        name = club.club_name
        club.delete()
        messages.success(request, f"Club '{name}' deleted successfully.")
    return redirect("admin_view_clubs")


def admin_view_turfs(request):
    if not _admin_required(request):
        return redirect("admin_login")

    turfs = Turf.objects.select_related("turf_owner").annotate(
        booking_count=Count("booking", distinct=True)
    )

    name = request.GET.get("name")
    location = request.GET.get("location")
    sort = request.GET.get("sort")

    if name:
        turfs = turfs.filter(turf_name__icontains=name)
    if location:
        turfs = turfs.filter(
            Q(turf_location__icontains=location)
            | Q(turf_district__icontains=location)
        )
    if sort == "high":
        turfs = turfs.order_by("-turf_rate")
    elif sort == "low":
        turfs = turfs.order_by("turf_rate")
    else:
        turfs = turfs.order_by("-turf_id")

    return render(request, "admin/admin_view_turfs.html", {"turfs": turfs})


def validate_turf(request, turf_id):
    if not _admin_required(request):
        return redirect("admin_login")
    turf = get_object_or_404(Turf, turf_id=turf_id)
    if request.method == "POST":
        turf.is_validated = True
        turf.validated_at = timezone.now()
        turf.save()
        messages.success(request, f"Turf '{turf.turf_name}' validated successfully.")
    return redirect("admin_view_turfs")


def delete_turf(request, turf_id):
    if not _admin_required(request):
        return redirect("admin_login")
    turf = get_object_or_404(Turf, turf_id=turf_id)
    if request.method == "POST":
        name = turf.turf_name
        turf.delete()
        messages.success(request, f"Turf '{name}' deleted successfully.")
    return redirect("admin_view_turfs")

def admin_view_matches(request):
    if not _admin_required(request):
        return redirect("admin_login")

    base_qs = Match.objects.select_related(
        "match_home_team", "match_away_team", "match_turf",
    )

    scheduled_matches = list(
        base_qs.filter(match_started=False, match_finished=False).order_by(
            "match_date", "match_time"
        )
    )

    live_matches = list(
        base_qs.filter(match_started=True, match_finished=False).order_by("-match_date")
    )
    for match in live_matches:
        _attach_match_result(match)

    completed_matches = list(
        base_qs.filter(match_finished=True).order_by("-match_date", "-match_id")
    )
    for match in completed_matches:
        _attach_match_result(match)

    return render(request, "admin/admin_view_matches.html", {
        "scheduled_matches": scheduled_matches,
        "live_matches": live_matches,
        "completed_matches": completed_matches,
    })


def admin_view_match_detail(request, match_id):
    """Detailed match view with all events and video."""
    if not _admin_required(request):
        return redirect("admin_login")
    
    match = get_object_or_404(
        Match.objects.select_related(
            "match_home_team", "match_away_team", "match_turf"
        ),
        match_id=match_id
    )
    
    _attach_match_result(match)
    
    # Get squads
    home_squad = match.home_squad.select_related('player_club', 'player_position').all()
    home_subs = match.home_subs.select_related('player_club', 'player_position').all()
    away_squad = match.away_squad.select_related('player_club', 'player_position').all() if match.match_away_team else []
    away_subs = match.away_subs.select_related('player_club', 'player_position').all() if match.match_away_team else []
    
    context = {
        "match": match,
        "home_squad": home_squad,
        "home_subs": home_subs,
        "away_squad": away_squad,
        "away_subs": away_subs,
        "goals": match.goals,
        "assists": match.assists,
        "saves": match.saves,
        "result": match.result,
        "has_video": match.result and match.result.result_video,
    }
    return render(request, "admin/admin_match_detail.html", context)


def admin_delete_match(request, match_id):
    if not _admin_required(request):
        return redirect("admin_login")
    match = get_object_or_404(Match, match_id=match_id)
    if request.method == "POST":
        home = match.match_home_team.club_name
        away = match.match_away_team.club_name if match.match_away_team else "TBD"
        match.delete()
        messages.success(request, f"Match {home} vs {away} deleted successfully.")
    return redirect("admin_view_matches")




def admin_delete_tournament(request, t_id):
    if not _admin_required(request):
        return redirect("admin_login")
    tournament = get_object_or_404(Tournament, t_id=t_id)
    if request.method == "POST":
        name = tournament.t_name or "Unnamed Tournament"
        tournament.delete()
        messages.success(request, f"Tournament '{name}' deleted successfully.")
    return redirect("admin_view_tournaments")


def admin_view_time_schedules(request):
    if not _admin_required(request):
        return redirect("admin_login")
    schedules = Time_Schedule.objects.annotate(
        turf_count=Count("turf_time_map", distinct=True)
    ).order_by("time_id")
    return render(request, "admin/admin_view_time_schedule.html", {
        "schedules": schedules,
    })


def admin_view_turf_time_maps(request):
    if not _admin_required(request):
        return redirect("admin_login")
    maps = Turf_time_map.objects.select_related("tt_time", "tt_turf").order_by("-tt_id")
    return render(request, "admin/admin_view_turf_time_maps.html", {"maps": maps})

def admin_view_bookings(request):
    if not _admin_required(request):
        return redirect("admin_login")

    customer_club = Club.objects.filter(
        club_manager=OuterRef('customer')
    ).values('club_name')[:1]

    bookings = Booking.objects.select_related(
        "turf", "customer", "club", "time_slot__tt_time"
    ).annotate(
        manager_club_name=Subquery(customer_club)  # NEW
    ).order_by("-booking_id")

    status_filter = request.GET.get("status", "all")
    turf = request.GET.get("turf")
    customer = request.GET.get("customer")

    if status_filter != "all":
        bookings = bookings.filter(status=status_filter)
    if turf:
        bookings = bookings.filter(turf__turf_name__icontains=turf)
    if customer:
        bookings = bookings.filter(
            Q(customer__user_name__icontains=customer)
            | Q(customer__user_email__icontains=customer)
        )

    return render(request, "admin/admin_view_bookings.html", {
        "bookings": bookings,
        "status_filter": status_filter,
    })


def admin_update_booking_status(request, booking_id):
    if not _admin_required(request):
        return redirect("admin_login")
    booking = get_object_or_404(Booking, booking_id=booking_id)
    if request.method == "POST":
        new_status = request.POST.get("status")
        if new_status in ["Pending", "Accepted", "Rejected"]:
            booking.status = new_status
            booking.save()
            messages.success(request, f"Booking status updated to {new_status}.")
    return redirect("admin_view_bookings")


def admin_view_payments(request):
    if not _admin_required(request):
        return redirect("admin_login")

    payments = Payment.objects.select_related(
        "booking__turf", "booking__customer"
    ).order_by("-payment_id")

    status_filter = request.GET.get("status", "all")
    if status_filter != "all":
        payments = payments.filter(payment_status=status_filter)

    # Divide by 100 to convert paise → rupees
    total_success = (Payment.objects.filter(payment_status="Success").aggregate(
        s=Sum("amount")
    )["s"] or 0) // 100

    total_pending = (Payment.objects.filter(payment_status="Pending").aggregate(
        s=Sum("amount")
    )["s"] or 0) // 100

    return render(request, "admin/admin_view_payments.html", {
        "payments": payments,
        "status_filter": status_filter,
        "total_success": total_success,
        "total_pending": total_pending,
    })

def admin_view_notifications(request):
    if not _admin_required(request):
        return redirect("admin_login")

    notifications = Notification.objects.select_related("user").order_by("-created_at")
    type_filter = request.GET.get("type", "all")
    read_filter = request.GET.get("read", "all")

    if type_filter != "all":
        notifications = notifications.filter(notification_type=type_filter)
    if read_filter == "read":
        notifications = notifications.filter(is_read=True)
    elif read_filter == "unread":
        notifications = notifications.filter(is_read=False)

    return render(request, "admin/admin_view_notifications.html", {
        "notifications": notifications,
        "type_filter": type_filter,
        "read_filter": read_filter,
    })


def admin_mark_notification_read(request, notif_id):
    if not _admin_required(request):
        return redirect("admin_login")
    notif = get_object_or_404(Notification, id=notif_id)
    notif.is_read = True
    notif.save()
    messages.success(request, "Notification marked as read.")
    return redirect("admin_view_notifications")


def admin_view_tournaments(request):
    """View all tournaments with full stats and management options."""
    if not _admin_required(request):
        return redirect("admin_login")

    tournaments = Tournament.objects.select_related("t_host").annotate(
        club_count=Count("t_club_map", distinct=True),
        match_count=Count("matches", distinct=True),
        finished_match_count=Count("matches", filter=Q(matches__match_finished=True), distinct=True)
    ).order_by("-t_date")

    for t in tournaments:
        t.clubs = T_club_map.objects.filter(t_c_tournament=t).select_related("t_c_club")
        t.paid_count = T_club_map.objects.filter(t_c_tournament=t, is_paid=True).count()
        t.revenue = t.paid_count * t.registration_fee

    status_filter = request.GET.get("status", "all")
    if status_filter == "active":
        tournaments = tournaments.filter(is_active=True, is_completed=False)
    elif status_filter == "completed":
        tournaments = tournaments.filter(is_completed=True)
    elif status_filter == "upcoming":
        tournaments = tournaments.filter(t_date__gt=date.today(), is_active=True)

    context = {
        "tournaments": tournaments,
        "status_filter": status_filter,
        "total_count": Tournament.objects.count(),
        "active_count": Tournament.objects.filter(is_active=True, is_completed=False).count(),
        "completed_count": Tournament.objects.filter(is_completed=True).count(),
    }
    return render(request, "admin/admin_view_tournaments.html", context)


def admin_view_tournament_detail(request, t_id):
    """Detailed tournament view with bracket, standings, matches, and registrations."""
    if not _admin_required(request):
        return redirect("admin_login")

    tournament = get_object_or_404(
        Tournament.objects.select_related("t_host", "t_host__club_manager"),
        t_id=t_id
    )

    # Recalculate all stats
    all_registrations = T_club_map.objects.filter(t_c_tournament=tournament)
    for reg in all_registrations:
        reg.update_stats()

    registrations = T_club_map.objects.filter(
        t_c_tournament=tournament
    ).select_related('t_c_club').order_by('-points', '-goals_for', 'goals_against')

    # Group standings
    group_standings = {}
    if tournament.format == 'hybrid':
        groups = T_club_map.objects.filter(
            t_c_tournament=tournament,
            group_name__isnull=False
        ).values_list('group_name', flat=True).distinct().order_by('group_name')

        for group in groups:
            group_teams = T_club_map.objects.filter(
                t_c_tournament=tournament,
                group_name=group
            ).select_related('t_c_club').order_by('-points', '-goals_for', 'goals_against')
            group_standings[group] = group_teams

   
    # All matches
    matches = list(Match.objects.filter(
        tournament=tournament
    ).select_related('match_home_team', 'match_away_team', 'match_turf').order_by('round_number', 'match_date'))

    for match in matches:
        match.result_obj = Result.objects.filter(result_match=match).first()

    group_matches = [m for m in matches if not m.is_knockout]
    knockout_matches = [m for m in matches if m.is_knockout]

    # Build bracket data
    bracket = {}
    for match in knockout_matches:
        r = match.round_number
        if r not in bracket:
            bracket[r] = []
        result = Result.objects.filter(result_match=match).first()
        bracket[r].append({
            'match': match,
            'result': result,
            'home_score': result.result_home_team if result else 0,
            'away_score': result.result_away_team if result else 0,
        })

    bracket_rounds = []
    for round_num in sorted(bracket.keys()):
        matches_in_round = bracket[round_num]
        num_matches = len(matches_in_round)
        teams_in_round = num_matches * 2

        if teams_in_round >= 16:
            round_name = 'Round of 16'
        elif teams_in_round == 8:
            round_name = 'Quarterfinals'
        elif teams_in_round == 4:
            round_name = 'Semifinals'
        elif teams_in_round == 2:
            round_name = 'Final'
        else:
            round_name = f'Round {round_num}'

        bracket_rounds.append({
            'round_num': round_num,
            'round_name': round_name,
            'matches': matches_in_round,
        })

    # Payments
    payments = TournamentPayment.objects.filter(
        tournament_registration__t_c_tournament=tournament
    ).select_related('tournament_registration__t_c_club').order_by('-created_at')

    total_revenue = payments.filter(payment_status="Success").aggregate(
        total=Sum('amount')
    )['total'] or 0

    context = {
        "tournament": tournament,
        "registrations": registrations,
        "group_standings": group_standings,
        "group_matches": group_matches,
        "knockout_matches": knockout_matches,
        "bracket_rounds": bracket_rounds,
        "payments": payments,
        "total_revenue": total_revenue,
        "pending_squad_count": Match.objects.filter(
            tournament=tournament,
            match_finished=False
        ).filter(
            Q(match_home_team__isnull=False, home_squad_selected=False) |
            Q(match_away_team__isnull=False, away_squad_selected=False)
        ).count(),
    }
    return render(request, "admin/admin_tournament_detail.html", context)


def admin_edit_tournament(request, t_id):
    if not _admin_required(request):
        return redirect("admin_login")

    tournament = get_object_or_404(Tournament, t_id=t_id)

    if request.method == "POST":
        tournament.t_name = request.POST.get("tournament_name", tournament.t_name)
        tournament.t_date = request.POST.get("tournament_date", tournament.t_date)
        tournament.registration_fee = request.POST.get("registration_fee", tournament.registration_fee)
        tournament.prize_pool = request.POST.get("prize_pool", tournament.prize_pool) or None
        tournament.max_teams = request.POST.get("max_teams", tournament.max_teams)
        tournament.registration_deadline = request.POST.get("registration_deadline") or tournament.registration_deadline
        tournament.description = request.POST.get("description", tournament.description)
        tournament.format = request.POST.get("format", tournament.format)
        tournament.teams_per_group = request.POST.get("teams_per_group", tournament.teams_per_group)
        tournament.teams_qualifying = request.POST.get("teams_qualifying", tournament.teams_qualifying)
        tournament.squad_size = request.POST.get("squad_size", tournament.squad_size)
        tournament.is_active = request.POST.get("is_active") == "on"
        tournament.is_completed = request.POST.get("is_completed") == "on"
        tournament.save()

        messages.success(request, f"Tournament '{tournament.t_name}' updated successfully.")
        return redirect("admin_view_tournament_detail", t_id=t_id)

    context = {
        "tournament": tournament,
        "today": date.today().isoformat(),
        "squad_sizes": [(5, '5-a-side'), (7, '7-a-side'), (9, '9-a-side'), (11, '11-a-side'), (12, '12-a-side')],
        "formats": [('league', 'Round Robin'), ('knockout', 'Knockout'), ('hybrid', 'Group Stage + Knockout')],
    }
    return render(request, "admin/admin_edit_tournament.html", context)


def admin_delete_tournament(request, t_id):
    if not _admin_required(request):
        return redirect("admin_login")

    tournament = get_object_or_404(Tournament, t_id=t_id)
    if request.method == "POST":
        name = tournament.t_name or "Unnamed Tournament"
        tournament.delete()
        messages.success(request, f"Tournament '{name}' deleted successfully.")
    return redirect("admin_view_tournaments")


def admin_tournament_registrations(request, t_id):
    if not _admin_required(request):
        return redirect("admin_login")

    tournament = get_object_or_404(Tournament, t_id=t_id)
    registrations = T_club_map.objects.filter(
        t_c_tournament=tournament
    ).select_related('t_c_club', 't_c_club__club_manager').order_by('-t_c_id')

    # Update stats for all
    for reg in registrations:
        reg.update_stats()

    context = {
        "tournament": tournament,
        "registrations": registrations,
        "paid_count": registrations.filter(is_paid=True).count(),
        "unpaid_count": registrations.filter(is_paid=False).count(),
    }
    return render(request, "admin/admin_tournament_registrations.html", context)


def admin_update_registration_status(request, t_c_id):
    if not _admin_required(request):
        return redirect("admin_login")

    registration = get_object_or_404(T_club_map, t_c_id=t_c_id)
    tournament_id = registration.t_c_tournament.t_id

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "toggle_payment":
            registration.is_paid = not registration.is_paid
            if registration.is_paid:
                registration.paid_at = timezone.now()
            registration.save()
            status = "paid" if registration.is_paid else "unpaid"
            messages.success(request, f"Registration marked as {status}.")
        elif action == "remove":
            club_name = registration.t_c_club.club_name
            registration.delete()
            messages.success(request, f"{club_name} removed from tournament.")

    return redirect("admin_tournament_registrations", t_id=tournament_id)


def admin_tournament_matches(request, t_id):
    if not _admin_required(request):
        return redirect("admin_login")

    tournament = get_object_or_404(Tournament, t_id=t_id)
    
    # Evaluate to list so attached attributes persist
    matches = list(Match.objects.filter(
        tournament=tournament
    ).select_related(
        'match_home_team', 'match_away_team', 'match_turf'
    ).order_by('round_number', 'match_date'))

    for match in matches:
        match.result_obj = Result.objects.filter(result_match=match).first()
        match.home_goals = Goal.objects.filter(
            result__result_match=match, for_club=match.match_home_team
        ).count() if match.match_home_team else 0
        match.away_goals = Goal.objects.filter(
            result__result_match=match, for_club=match.match_away_team
        ).count() if match.match_away_team else 0

    group_matches = [m for m in matches if not m.is_knockout]
    knockout_matches = [m for m in matches if m.is_knockout]

    context = {
        "tournament": tournament,
        "matches": matches,
        "group_matches": group_matches,
        "knockout_matches": knockout_matches,
    }
    return render(request, "admin/admin_tournament_matches.html", context)
def admin_tournament_match_detail(request, match_id):
    """Detailed view of a tournament match for admin."""
    if not _admin_required(request):
        return redirect("admin_login")

    match = get_object_or_404(
        Match.objects.select_related(
            "match_home_team", "match_away_team", "match_turf", "tournament"
        ),
        match_id=match_id
    )

    _attach_match_result(match)

    home_squad = match.home_squad.select_related('player_club', 'player_position').all()
    home_subs = match.home_subs.select_related('player_club', 'player_position').all()
    away_squad = match.away_squad.select_related('player_club', 'player_position').all() if match.match_away_team else []
    away_subs = match.away_subs.select_related('player_club', 'player_position').all() if match.match_away_team else []



    goals = Goal.objects.filter(result=match.result) if match.result else []
    assists = Assist.objects.filter(result=match.result) if match.result else []
    saves = Save.objects.filter(result=match.result) if match.result else []

    for g in goals: g.achievement_type = 'goal'
    for a in assists: a.achievement_type = 'assist'
    for s in saves: s.achievement_type = 'save'

    match_start = None
    if match.match_started and match.match_date and match.match_time:
        time_str = str(match.match_time).strip()
        start_time_match = re.match(r'(\d{1,2}):(\d{2})', time_str)
        if start_time_match:
            hour = int(start_time_match.group(1))
            minute = int(start_time_match.group(2))
            match_time_obj = dt_time(hour, minute)
            match_start = datetime.combine(match.match_date, match_time_obj)
            if timezone.is_naive(match_start):
                match_start = timezone.make_aware(match_start)

    for ach in chain(goals, assists, saves):
        if match_start and ach.time:
            delta = ach.time - match_start
            minutes = int(delta.total_seconds() // 60)
            ach.match_minute = max(1, min(minutes, 120))
        else:
            ach.match_minute = "--"

    achievements = sorted(chain(goals, assists, saves), key=attrgetter('time'), reverse=True)

    context = {
        "match": match,
        "home_squad": home_squad,
        "home_subs": home_subs,
        "away_squad": away_squad,
        "away_subs": away_subs,
        "goals": match.goals,
        "assists": match.assists,
        "saves": match.saves,
        "achievements": achievements,
        "result": match.result,
        "has_video": match.result and match.result.result_video if hasattr(match, 'result') else False,
    }
    return render(request, "admin/admin_tournament_match_detail.html", context)


def admin_tournament_bracket(request, t_id):
    """Visual bracket view for admin."""
    if not _admin_required(request):
        return redirect("admin_login")

    tournament = get_object_or_404(Tournament, t_id=t_id)

    from django.db.models import Q
    knockout_matches = Match.objects.filter(
        tournament=tournament,
        is_knockout=True
    ).exclude(
        match_home_team__isnull=True,
        match_away_team__isnull=True,
        match_started=False,
        match_finished=False
    ).select_related('match_home_team', 'match_away_team').order_by('round_number', 'bracket_position', 'match_id')

    bracket = {}
    for match in knockout_matches:
        round_num = match.round_number
        if round_num not in bracket:
            bracket[round_num] = []
        result = Result.objects.filter(result_match=match).first()
        bracket[round_num].append({
            'match': match,
            'result': result,
            'home_score': result.result_home_team if result else 0,
            'away_score': result.result_away_team if result else 0,
        })

    bracket_rounds = []
    for round_num in sorted(bracket.keys()):
        matches = bracket[round_num]
        num_matches = len(matches)
        teams_in_round = num_matches * 2

        if teams_in_round >= 16:
            round_name = 'Round of 16'
        elif teams_in_round == 8:
            round_name = 'Quarterfinals'
        elif teams_in_round == 4:
            round_name = 'Semifinals'
        elif teams_in_round == 2:
            round_name = 'Final'
        else:
            round_name = f'Round {round_num}'

        bracket_rounds.append({
            'round_num': round_num,
            'round_name': round_name,
            'matches': matches,
        })

    context = {
        "tournament": tournament,
        "bracket_rounds": bracket_rounds,
    }
    return render(request, "admin/admin_tournament_bracket.html", context)


def admin_tournament_payments(request, t_id):
    """View all tournament payments."""
    if not _admin_required(request):
        return redirect("admin_login")

    tournament = get_object_or_404(Tournament, t_id=t_id)
    payments = TournamentPayment.objects.filter(
        tournament_registration__t_c_tournament=tournament
    ).select_related('tournament_registration__t_c_club').order_by('-created_at')

    total_collected = payments.filter(payment_status="Success").aggregate(
        total=Sum('amount')
    )['total'] or 0

    total_pending = payments.filter(payment_status="Pending").aggregate(
        total=Sum('amount')
    )['total'] or 0

    context = {
        "tournament": tournament,
        "payments": payments,
        "total_collected": total_collected,
        "total_pending": total_pending,
        "success_count": payments.filter(payment_status="Success").count(),
        "pending_count": payments.filter(payment_status="Pending").count(),
        "failure_count": payments.filter(payment_status="Failure").count(),
    }
    return render(request, "admin/admin_tournament_payments.html", context)


def admin_force_end_match(request, match_id):
    """Admin can force-end any tournament match."""
    if not _admin_required(request):
        return redirect("admin_login")

    match = get_object_or_404(Match, match_id=match_id)

    if request.method == "POST":
        match.match_finished = True
        match.save()

        # Update stats if group stage
        if match.tournament and not match.is_knockout:
            home_reg = T_club_map.objects.filter(
                t_c_tournament=match.tournament,
                t_c_club=match.match_home_team
            ).first()
            away_reg = T_club_map.objects.filter(
                t_c_tournament=match.tournament,
                t_c_club=match.match_away_team
            ).first()
            if home_reg:
                home_reg.update_stats()
            if away_reg:
                away_reg.update_stats()

        # Advance knockout winner
        if match.is_knockout:
            from user_app.views import advance_knockout_winner
            advance_knockout_winner(match)

        messages.success(request, f"Match force-ended by admin.")

    if match.tournament:
        return redirect("admin_tournament_matches", t_id=match.tournament.t_id)
    return redirect("admin_view_matches")


def admin_update_match_score(request, match_id):
    """Admin can directly update match scores."""
    if not _admin_required(request):
        return redirect("admin_login")

    match = get_object_or_404(Match, match_id=match_id)

    if request.method == "POST":
        try:
            home_score = int(request.POST.get("home_score", 0))
            away_score = int(request.POST.get("away_score", 0))
        except ValueError:
            messages.error(request, "Invalid score values.")
            return redirect("admin_tournament_match_detail", match_id=match_id)

        result, created = Result.objects.get_or_create(result_match=match)
        result.result_home_team = home_score
        result.result_away_team = away_score
        result.save()

        messages.success(request, f"Score updated: {home_score} - {away_score}")

    if match.tournament:
        return redirect("admin_tournament_match_detail", match_id=match_id)
    return redirect("admin_view_match_detail", match_id=match_id)
