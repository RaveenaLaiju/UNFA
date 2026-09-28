from django.db import models
from visitor_app.models import User


class Position(models.Model):
    position_id = models.AutoField(primary_key=True)
    position_name = models.CharField(max_length=100)
    position_code = models.CharField(max_length=10)
    position_description = models.TextField()

    def __str__(self):
        return self.position_name


class Turf(models.Model):
    turf_id = models.AutoField(primary_key=True)
    turf_owner = models.ForeignKey(User, on_delete=models.CASCADE)
    turf_name = models.CharField(max_length=200)
    turf_rate = models.IntegerField()
    turf_district = models.CharField(max_length=100)
    turf_location = models.CharField(max_length=100)
    turf_image = models.ImageField(upload_to="turfs/")
    is_validated = models.BooleanField(default=False)
    validated_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.turf_name


class Club(models.Model):
    club_id = models.AutoField(primary_key=True)
    # FIXED: Changed from OneToOneField to ForeignKey
    # This allows one manager to manage multiple clubs
    club_manager = models.ForeignKey(User, on_delete=models.CASCADE)
    club_name = models.CharField(max_length=200, unique=True)
    club_district = models.CharField(max_length=100)
    club_location = models.CharField(max_length=100)
    club_weight = models.IntegerField(default=10, null=True)
    club_home_ground = models.ForeignKey(Turf, on_delete=models.CASCADE, null=True, blank=True)
    club_logo = models.ImageField(upload_to="club_logo/")
    is_validated = models.BooleanField(default=False)
    validated_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.club_name


class Player(models.Model):
    player_id = models.AutoField(primary_key=True)
    # OneToOneField is correct - one player card per user
    player_user = models.OneToOneField(User, on_delete=models.CASCADE)
    player_card_name = models.CharField(max_length=20)
    player_rating = models.IntegerField(default=50)
    player_club = models.ForeignKey(Club, on_delete=models.CASCADE, null=True, blank=True)
    player_position = models.ForeignKey(Position, on_delete=models.CASCADE)
    player_strong_foot = models.CharField(max_length=10)
    player_weight = models.IntegerField()
    player_height = models.IntegerField()
    player_power = models.IntegerField()
    player_district = models.CharField(max_length=100)
    player_location = models.CharField(max_length=100)
    player_image = models.ImageField(upload_to="players/")

    def __str__(self):
        return self.player_card_name


class Time_Schedule(models.Model):
    time_id = models.AutoField(primary_key=True)
    time_range = models.CharField(max_length=100)

    def __str__(self):
        return self.time_range


class Turf_time_map(models.Model):
    tt_id = models.AutoField(primary_key=True)
    tt_time = models.ForeignKey(Time_Schedule, on_delete=models.CASCADE)
    tt_turf = models.ForeignKey(Turf, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.tt_turf.turf_name} - {self.tt_time.time_range}"


class Match(models.Model):
    match_id = models.AutoField(primary_key=True)
    match_home_team = models.ForeignKey(Club,on_delete=models.CASCADE,related_name='home_team',null=True,blank=True)
    match_away_team = models.ForeignKey(Club,on_delete=models.CASCADE,related_name='away_team',null=True,blank=True)
    match_turf = models.ForeignKey(Turf,on_delete=models.CASCADE)
    match_date = models.DateField()
    match_time = models.TimeField(null=True,blank=True)
    match_started = models.BooleanField(default=False)
    match_started_at = models.DateTimeField(null=True,blank=True)
    match_finished = models.BooleanField(default=False)
    match_finished_at = models.DateTimeField(null=True,blank=True)
    match_duration = models.PositiveIntegerField(default=5400,help_text="Total match duration in seconds")
    match_elapsed_seconds = models.PositiveIntegerField(default=0,help_text="Seconds already elapsed before the current timer run")
    match_paused = models.BooleanField(default=False)
    match_paused_at = models.DateTimeField(null=True,blank=True)
    tournament = models.ForeignKey('Tournament',on_delete=models.CASCADE,null=True,blank=True,related_name='matches')
    round_number = models.IntegerField(default=1,help_text="Round number in tournament (1=group stage, 2=quarters, 3=semis, 4=final)")
    is_knockout = models.BooleanField(default=False,help_text="True for knockout rounds")
    home_squad = models.ManyToManyField(Player,related_name="home_squad",blank=True)
    home_subs = models.ManyToManyField(Player,related_name="home_subs",blank=True)
    away_squad = models.ManyToManyField(Player,related_name="away_squad",blank=True)
    away_subs = models.ManyToManyField(Player,related_name="away_subs",blank=True)
    bracket_position = models.IntegerField(default=0,help_text="Position in knockout bracket (0-indexed)")
    squad_size = models.PositiveSmallIntegerField(default=5,help_text="Number of starting players for this match")
    home_squad_selected = models.BooleanField(default=False,help_text="True when home team squad has been selected")
    away_squad_selected = models.BooleanField(default=False,help_text="True when away team squad has been selected")

    def __str__(self):
        home = self.match_home_team.club_name if self.match_home_team else "TBD"
        away = self.match_away_team.club_name if self.match_away_team else "TBD"

        return f"{home} vs {away}"

class Result(models.Model):
    result_id = models.AutoField(primary_key=True)
    result_match = models.OneToOneField(Match, on_delete=models.CASCADE)
    result_home_team = models.IntegerField(default=0)
    result_away_team = models.IntegerField(default=0)
    result_video = models.FileField(upload_to="match_videos/", null=True, blank=True)

    def __str__(self):
        return f"Result for Match {self.result_match.match_id}"


class Goal(models.Model):
    goal_id = models.AutoField(primary_key=True)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    result = models.ForeignKey(Result, on_delete=models.CASCADE)
    for_club = models.ForeignKey(Club, on_delete=models.CASCADE, null=True, blank=True)
    time = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Goal by {self.player.player_card_name}"


class Assist(models.Model):
    assist_id = models.AutoField(primary_key=True)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    result = models.ForeignKey(Result, on_delete=models.CASCADE)
    for_club = models.ForeignKey(Club, on_delete=models.CASCADE, null=True, blank=True)
    time = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Assist by {self.player.player_card_name}"


class Save(models.Model):
    save_id = models.AutoField(primary_key=True)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    result = models.ForeignKey(Result, on_delete=models.CASCADE)
    for_club = models.ForeignKey(Club, on_delete=models.CASCADE, null=True, blank=True)
    time = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Save by {self.player.player_card_name}"


class Tournament(models.Model):
    t_id = models.AutoField(primary_key=True)
    t_name = models.CharField(max_length=100, null=True, blank=True)
    t_host = models.ForeignKey(Club, on_delete=models.CASCADE)
    t_date = models.DateField()

    # NEW: Tournament fee for registration
    registration_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Fee required to join tournament")
    prize_pool = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, null=True, blank=True)
    max_teams = models.IntegerField(default=16, help_text="Maximum number of teams allowed")
    registration_deadline = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True, help_text="Tournament is currently running")
    is_completed = models.BooleanField(default=False, help_text="Tournament has finished")
    description = models.TextField(null=True, blank=True)
    SQUAD_SIZE_CHOICES = [
        (5, '5-a-side'),
        (7, '7-a-side'),
        (9, '9-a-side'),
        (11, '11-a-side'),
        (12, '12-a-side'),
    ]
    squad_size = models.PositiveSmallIntegerField(
        choices=SQUAD_SIZE_CHOICES,
        default=5,
        help_text="Number of starting players per team in tournament matches"
    )

    # Whether squads have been selected for this tournament
    squads_selected = models.BooleanField(
        default=False,
        help_text="True when all tournament match squads have been configured"
    )
    # Tournament format
    FORMAT_CHOICES = [
        ('league', 'Round Robin (League)'),
        ('knockout', 'Knockout (Single Elimination)'),
        ('hybrid', 'Group Stage + Knockout'),
    ]
    format = models.CharField(max_length=20, choices=FORMAT_CHOICES, default='hybrid')

    # For group stage
    teams_per_group = models.IntegerField(default=4, help_text="Teams per group in hybrid format")
    teams_qualifying = models.IntegerField(default=2, help_text="Teams qualifying from each group")

    def __str__(self):
        return self.t_name or "Unnamed Tournament"

    @property
    def registered_teams_count(self):
        return self.t_club_map_set.count()

    @property
    def is_full(self):
        return self.registered_teams_count >= self.max_teams

    @property
    def status_display(self):
        if self.is_completed:
            return "Completed"
        elif self.is_active:
            if self.matches.exists():
                return "In Progress"
            return "Registration Open"
        return "Inactive"


class T_club_map(models.Model):
    t_c_id = models.AutoField(primary_key=True)
    t_c_tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE)
    t_c_club = models.ForeignKey(Club, on_delete=models.CASCADE)

    # NEW: Payment tracking for tournament registration
    is_paid = models.BooleanField(default=False)
    payment_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    paid_at = models.DateTimeField(null=True, blank=True)

    # Group assignment for hybrid format
    group_name = models.CharField(max_length=10, null=True, blank=True, help_text="A, B, C, etc.")

    # Stats for points table
    played = models.IntegerField(default=0)
    won = models.IntegerField(default=0)
    drawn = models.IntegerField(default=0)
    lost = models.IntegerField(default=0)
    goals_for = models.IntegerField(default=0)
    goals_against = models.IntegerField(default=0)
    points = models.IntegerField(default=0)

    class Meta:
        unique_together = ('t_c_tournament', 't_c_club')

    def __str__(self):
        return f"{self.t_c_club.club_name} in {self.t_c_tournament.t_name}"

    @property
    def goal_difference(self):
        return self.goals_for - self.goals_against

    def update_stats(self):
        """Recalculate stats from tournament matches"""
        matches = Match.objects.filter(
            tournament=self.t_c_tournament,
            match_finished=True
        ).filter(
            models.Q(match_home_team=self.t_c_club) | models.Q(match_away_team=self.t_c_club)
        )

        self.played = matches.count()
        self.won = 0
        self.drawn = 0
        self.lost = 0
        self.goals_for = 0
        self.goals_against = 0
        self.points = 0

        for match in matches:
            result = Result.objects.filter(result_match=match).first()
            if not result:
                continue

            if match.match_home_team == self.t_c_club:
                self.goals_for += result.result_home_team
                self.goals_against += result.result_away_team
                if result.result_home_team > result.result_away_team:
                    self.won += 1
                    self.points += 3
                elif result.result_home_team == result.result_away_team:
                    self.drawn += 1
                    self.points += 1
                else:
                    self.lost += 1
            else:
                self.goals_for += result.result_away_team
                self.goals_against += result.result_home_team
                if result.result_away_team > result.result_home_team:
                    self.won += 1
                    self.points += 3
                elif result.result_away_team == result.result_home_team:
                    self.drawn += 1
                    self.points += 1
                else:
                    self.lost += 1

        self.save()
        
class TournamentPayment(models.Model):
    """Payment record for tournament registration"""
    tp_id = models.AutoField(primary_key=True)
    tournament_registration = models.ForeignKey(T_club_map, on_delete=models.CASCADE)
    provider_order_id = models.CharField(max_length=100)
    razorpay_payment_id = models.CharField(max_length=100, null=True, blank=True)
    signature_id = models.CharField(max_length=100, null=True, blank=True)
    payment_status = models.CharField(
        max_length=10,
        choices=[("Pending", "Pending"), ("Success", "Success"), ("Failure", "Failure")],
        default="Pending"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Tournament Payment {self.provider_order_id} - {self.payment_status}"

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=20,
        default='info',
        choices=[
            ('info', 'Info'),
            ('success', 'Success'),
            ('error', 'Error')
        ]
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.user.user_name}: {self.message[:50]}..."


class Booking(models.Model):
    booking_id = models.AutoField(primary_key=True)
    turf = models.ForeignKey(Turf, on_delete=models.CASCADE)
    customer = models.ForeignKey(User, on_delete=models.CASCADE)
    club = models.ForeignKey(Club, on_delete=models.CASCADE, null=True, blank=True)
    time_slot = models.ForeignKey(Turf_time_map, on_delete=models.CASCADE)
    booking_date = models.DateField()
    status = models.CharField(
        max_length=10,
        choices=[("Pending", "Pending"), ("Accepted", "Accepted"), ("Rejected", "Rejected")],
        default="Pending"
    )
    is_paid = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.customer.user_name} - {self.turf.turf_name} ({self.booking_date})"


class Payment(models.Model):
    payment_id = models.AutoField(primary_key=True)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE)
    provider_order_id = models.CharField(max_length=100)
    razorpay_payment_id = models.CharField(max_length=100, null=True, blank=True)
    signature_id = models.CharField(max_length=100, null=True, blank=True)
    payment_status = models.CharField(
        max_length=10,
        choices=[("Pending", "Pending"), ("Success", "Success"), ("Failure", "Failure")],
        default="Pending"
    )
    amount = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment {self.provider_order_id} - {self.payment_status}"
