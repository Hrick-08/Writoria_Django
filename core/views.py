from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login, authenticate
from django.db.models import Q
from .models import BlogPost, UserProfile, Bookmark, BlogImage, Vote, Comment, ContactMessage
from django.contrib.auth.models import User
from .forms import BlogPostForm, UserProfileForm, CustomUserCreationForm, CommentForm
import random
import json

def home(request):
    posts = BlogPost.objects.all().order_by('-created_at')[:6]
    return render(request, 'core/home.html', {'posts': posts})

def about(request):
    return render(request, 'core/about.html')

def auth_view(request):
    login_form = AuthenticationForm()
    register_form = CustomUserCreationForm()
    
    if request.method == 'POST':
        action = request.POST.get('action', '')
        
        if action == 'login':
            login_form = AuthenticationForm(request, data=request.POST)
            if login_form.is_valid():
                username = login_form.cleaned_data.get('username')
                password = login_form.cleaned_data.get('password')
                user = authenticate(request, username=username, password=password)
                if user is not None:
                    login(request, user)
                    messages.success(request, 'Successfully logged in!')
                    return redirect('home')
                else:
                    messages.error(request, 'Invalid username or password.')
        elif action == 'register':
            register_form = CustomUserCreationForm(request.POST)
            if register_form.is_valid():
                user = register_form.save()
                login(request, user)
                messages.success(request, 'Account created successfully! Welcome to Writoria.')
                return redirect('home')
    
    return render(request, 'core/auth.html', {
        'login_form': login_form,
        'register_form': register_form
    })

class BlogListView(ListView):
    model = BlogPost
    template_name = 'core/blog_list.html'
    context_object_name = 'posts'
    ordering = ['-created_at']
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Get search query and category filter
        search_query = self.request.GET.get('search', '')
        category = self.request.GET.get('category', '')
        
        # Apply search filter
        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query) |
                Q(content__icontains=search_query)
            )
        
        # Apply category filter
        if category:
            queryset = queryset.filter(category=category)
        
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search', '')
        context['selected_category'] = self.request.GET.get('category', '')
        context['categories'] = BlogPost.CATEGORY_CHOICES
        return context

class BlogDetailView(DetailView):
    model = BlogPost
    template_name = 'core/blog_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context['is_bookmarked'] = Bookmark.objects.filter(
                user=self.request.user,
                post=self.object
            ).exists()
            context['user_vote'] = Vote.objects.filter(
                user=self.request.user,
                post=self.object
            ).first()
        context['comment_form'] = CommentForm()
        context['comments'] = self.object.comments.filter(parent=None)
        return context

class BlogCreateView(LoginRequiredMixin, CreateView):
    model = BlogPost
    form_class = BlogPostForm
    template_name = 'core/blog_form.html'

    def form_valid(self, form):
        form.instance.author = self.request.user
        response = super().form_valid(form)
        
        # Handle additional images
        images = self.request.FILES.getlist('images')
        captions = form.cleaned_data.get('image_captions', '').split('\n')
        captions = [cap.strip() for cap in captions if cap.strip()]
        
        for i, image in enumerate(images):
            caption = captions[i] if i < len(captions) else ''
            BlogImage.objects.create(
                post=self.object,
                image=image,
                caption=caption,
                order=i
            )
        
        return response

class BlogUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = BlogPost
    form_class = BlogPostForm
    template_name = 'core/blog_form.html'

    def form_valid(self, form):
        response = super().form_valid(form)
        
        # Handle additional images
        images = self.request.FILES.getlist('images')
        captions = form.cleaned_data.get('image_captions', '').split('\n')
        captions = [cap.strip() for cap in captions if cap.strip()]
        
        # Remove existing images if new ones are uploaded
        if images:
            self.object.images.all().delete()
            
            for i, image in enumerate(images):
                caption = captions[i] if i < len(captions) else ''
                BlogImage.objects.create(
                    post=self.object,
                    image=image,
                    caption=caption,
                    order=i
                )
        
        return response

    def test_func(self):
        post = self.get_object()
        return self.request.user == post.author

class BlogDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = BlogPost
    template_name = 'core/blog_confirm_delete.html'
    success_url = '/'

    def test_func(self):
        post = self.get_object()
        return self.request.user == post.author

@login_required
def toggle_bookmark(request, slug):
    post = get_object_or_404(BlogPost, slug=slug)
    bookmark, created = Bookmark.objects.get_or_create(
        user=request.user,
        post=post
    )
    if not created:
        bookmark.delete()
        is_bookmarked = False
    else:
        is_bookmarked = True
    return JsonResponse({'is_bookmarked': is_bookmarked})

@login_required
def vote_post(request, slug):
    post = get_object_or_404(BlogPost, slug=slug)
    
    try:
        vote = Vote.objects.get(user=request.user, post=post)
        # If user already gave life, remove it
        vote.delete()
        has_life = False
    except Vote.DoesNotExist:
        # Create new life
        Vote.objects.create(user=request.user, post=post, is_life=True)
        has_life = True
    
    # Update total lives
    total_lives = Vote.objects.filter(post=post, is_life=True).count()
    post.votes = total_lives
    post.save()
    
    return JsonResponse({
        'votes': total_lives,
        'has_life': has_life
    })

@login_required
def add_comment(request, slug):
    post = get_object_or_404(BlogPost, slug=slug)
    if request.method == 'POST':
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.post = post
            comment.author = request.user
            parent_id = request.POST.get('parent_id')
            if parent_id:
                comment.parent = Comment.objects.get(id=parent_id)
            comment.save()
            return JsonResponse({
                'status': 'success',
                'comment_id': comment.id,
                'author': comment.author.username,
                'content': comment.content,
                'created_at': comment.created_at.strftime('%b %d, %Y %H:%M'),
                'parent_id': parent_id
            })
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def delete_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    if request.user == comment.author:
        comment.delete()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'error': 'Unauthorized'}, status=403)

@login_required
def profile(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('profile')
    else:
        form = UserProfileForm(instance=profile)
    
    user_posts = BlogPost.objects.filter(author=request.user).order_by('-created_at')
    bookmarks = Bookmark.objects.filter(user=request.user).order_by('-created_at')
    lives_given = BlogPost.objects.filter(vote_set__user=request.user, vote_set__is_life=True)
    
    return render(request, 'core/profile.html', {
        'form': form,
        'user_posts': user_posts,
        'bookmarks': bookmarks,
        'lives_given': lives_given
    })

def user_profile(request, username):
    user = get_object_or_404(User, username=username)
    profile, created = UserProfile.objects.get_or_create(user=user)
    posts = BlogPost.objects.filter(author=user).order_by('-created_at')
    
    # Calculate profile completion
    completion_fields = {
        'avatar': bool(profile.avatar),
        'bio': bool(profile.bio),
        'website': bool(profile.website)
    }
    profile_completion = (sum(completion_fields.values()) / len(completion_fields)) * 100
    
    return render(request, 'core/user_profile.html', {
        'profile': profile,
        'posts': posts,
        'profile_completion': profile_completion
    })

def help_center(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        subject = request.POST.get('subject', 'No Subject')
        message = request.POST.get('message')
        
        if name and email and message:
            # Save the message to database
            ContactMessage.objects.create(
                name=name,
                email=email,
                subject=subject,
                message=message
            )
            
            messages.success(request, 'Your message has been sent successfully! We\'ll get back to you soon.')
            return JsonResponse({
                'status': 'success',
                'message': 'Your message has been sent successfully! We\'ll get back to you soon.',
                'redirect_url': '/'  # Redirect to homepage
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': 'Please fill in all required fields.'
            }, status=400)
        
    return render(request, 'core/help_center.html')

def team(request):
    context = {
        'divyam_image': 'img/1.jpg',
        'abhinav_image': 'img/2.jpg',
        'hrick_image': 'img/3.jpg',
        'harsh_image': 'img/4.jpg',
    }
    return render(request, 'core/team.html', context)
