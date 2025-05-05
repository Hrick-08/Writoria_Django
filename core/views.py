from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.http import JsonResponse, Http404
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login, authenticate
from django.db.models import Q
from .models import BlogPost, UserProfile, Bookmark, BlogImage, Vote, Comment, ContactMessage
from django.contrib.auth.models import User
from .forms import BlogPostForm, UserProfileForm, CustomUserCreationForm, CommentForm
import random
import json
from .services import APIClient

def home(request):
    # Get posts from Flask API first
    api_response, status_code = APIClient.get_blogs(
        request.api_token if request.user.is_authenticated else None
    )
    
    if status_code == 200:
        # Get all API blog IDs
        api_blog_ids = {post['id'] for post in api_response}
        
        # Delete any blogs that exist in Django but not in API
        BlogPost.objects.exclude(id__in=api_blog_ids).delete()
        
        # Sync any missing posts from API to Django
        for api_post in api_response:
            if not BlogPost.objects.filter(id=api_post['id']).exists():
                # Get or create the author user if author username is provided
                author = None
                if api_post.get('author'):
                    try:
                        author = User.objects.get(username=api_post['author'])
                    except User.DoesNotExist:
                        author = User.objects.create_user(
                            username=api_post['author'],
                            password=None  # This creates an unusable password
                        )
                
                if author:  # Only create blog post if we have an author
                    try:
                        # Create blog post with proper slug generation
                        post = BlogPost(
                            id=api_post['id'],
                            title=api_post['title'],
                            content=api_post['content'],
                            author=author,
                            created_at=api_post['timestamp']
                        )
                        # The save method will generate the slug
                        post.save()
                    except Exception as e:
                        print(f"Error creating blog post: {str(e)}")
                        continue

    # Get all posts from Django DB after syncing
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
                
                # First authenticate with Django
                user = authenticate(request, username=username, password=password)
                if user is not None:
                    login(request, user)
                    
                    # Then authenticate with Flask API
                    api_response, status_code = APIClient.login_user(username, password)
                    if status_code == 200:
                        # Store API token in session
                        request.session['api_token'] = api_response.get('access_token')
                        messages.success(request, 'Successfully logged in!')
                        return redirect('home')
                    else:
                        messages.warning(request, 'Logged in to Django but API login failed')
                        return redirect('home')
                else:
                    messages.error(request, 'Invalid username or password.')
            
        elif action == 'register':
            register_form = CustomUserCreationForm(request.POST)
            if register_form.is_valid():
                username = register_form.cleaned_data['username']
                
                # Check if username already exists
                if User.objects.filter(username=username).exists():
                    register_form.add_error('username', 'This username is already taken. Please choose another one.')
                else:
                    try:
                        # First register with Flask API
                        api_response, status_code = APIClient.register_user(
                            username,
                            register_form.cleaned_data['password1']
                        )
                        
                        if status_code == 201:
                            # If API registration successful, create Django user
                            user = register_form.save()
                            login(request, user)
                            
                            # Now login to get API token
                            api_login_response, login_status = APIClient.login_user(
                                username,
                                register_form.cleaned_data['password1']
                            )
                            
                            if login_status == 200:
                                request.session['api_token'] = api_login_response.get('access_token')
                                messages.success(request, 'Account created successfully! Welcome to Writoria.')
                                return redirect('home')
                        else:
                            register_form.add_error(None, f'Registration failed: {api_response.get("message", "Please try again.")}')
                    except Exception as e:
                        register_form.add_error(None, 'An error occurred during registration. Please try again.')
    
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
        
        # Get posts from Flask API
        api_response, status_code = APIClient.get_blogs(self.request.api_token if self.request.user.is_authenticated else None)
        if status_code == 200:
            # Get all API blog IDs
            api_blog_ids = {post['id'] for post in api_response}
            
            # Delete any blogs that exist in Django but not in API
            BlogPost.objects.exclude(id__in=api_blog_ids).delete()
            
            # Sync any missing posts from API to Django
            for api_post in api_response:
                if not BlogPost.objects.filter(id=api_post['id']).exists():
                    # Get or create the author user if author username is provided
                    author = None
                    if api_post.get('author'):
                        try:
                            author = User.objects.get(username=api_post['author'])
                        except User.DoesNotExist:
                            author = User.objects.create_user(
                                username=api_post['author'],
                                password=None  # This creates an unusable password
                            )
                    
                    if author:  # Only create blog post if we have an author
                        try:
                            # Create blog post with proper slug generation
                            post = BlogPost(
                                id=api_post['id'],
                                title=api_post['title'],
                                content=api_post['content'],
                                author=author,
                                created_at=api_post['timestamp']
                            )
                            # The save method will generate the slug
                            post.save()
                        except Exception as e:
                            print(f"Error creating blog post: {str(e)}")
                            continue
        
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
    context_object_name = 'object'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        
        # Check if blog still exists in API
        api_response, status_code = APIClient.get_blog(obj.id, self.request.session.get('api_token'))
        
        if status_code == 200:
            # Update content from API if needed
            obj.content = api_response.get('content', obj.content)
            obj.save()
        elif status_code == 404:
            obj.delete()
            messages.warning(self.request, 'This blog post has been deleted.')
            return None
            
        return obj

    def get(self, request, *args, **kwargs):
        try:
            self.object = self.get_object()
            if self.object is None:
                return redirect('blog_list')
            context = self.get_context_data(object=self.object)
            return self.render_to_response(context)
        except Http404:
            messages.warning(request, 'Blog post not found.')
            return redirect('blog_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get comments from Flask API
        api_response, status_code = APIClient.get_blog_comments(self.object.id)
        if status_code == 200:
            # Sync comments from API to Django if they don't exist
            api_comments = api_response
            for api_comment in api_comments:
                if not Comment.objects.filter(id=api_comment['id']).exists():
                    Comment.objects.create(
                        id=api_comment['id'],
                        post=self.object,
                        author=User.objects.get_or_create(username=api_comment['username'])[0],
                        content=api_comment['content'],
                        created_at=api_comment['timestamp']
                    )
        
        context['comments'] = self.object.comments.filter(parent=None)
        
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
        return context

class BlogCreateView(LoginRequiredMixin, CreateView):
    model = BlogPost
    form_class = BlogPostForm
    template_name = 'core/blog_form.html'

    def form_valid(self, form):
        # Set the author before any API calls
        form.instance.author = self.request.user
        
        try:
            # First create in Flask API
            api_response, status_code = APIClient.create_blog(
                self.request.session.get('api_token'),
                form.cleaned_data['title'],
                form.cleaned_data['content']
            )
            
            if status_code != 201:
                messages.error(self.request, f'Failed to create blog post in API: {api_response.get("message", "Unknown error")}')
                return self.form_invalid(form)
                
            # Set the ID from API response but preserve the author
            form.instance.id = api_response['blog']['id']
            
            try:
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
                messages.success(self.request, 'Blog post created successfully!')
                return response
                
            except Exception as e:
                # If Django save fails, attempt to delete from Flask API
                APIClient.delete_blog(api_response['blog']['id'], self.request.session.get('api_token'))
                messages.error(self.request, f'Failed to create blog post in Django: {str(e)}')
                return self.form_invalid(form)
                
        except Exception as e:
            messages.error(self.request, f'Failed to communicate with API: {str(e)}')
            return self.form_invalid(form)

class BlogUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = BlogPost
    form_class = BlogPostForm
    template_name = 'core/blog_form.html'

    def form_valid(self, form):
        form.instance.author = self.request.user
        response = super().form_valid(form)
        
        # Handle image updates
        images = self.request.FILES.getlist('images')
        captions = form.cleaned_data.get('image_captions', '').split('\n')
        captions = [cap.strip() for cap in captions if cap.strip()]
        
        # Delete existing images if replace_images is checked
        if form.cleaned_data.get('replace_images'):
            BlogImage.objects.filter(post=self.object).delete()
        
        # Add new images
        for i, image in enumerate(images):
            caption = captions[i] if i < len(captions) else ''
            BlogImage.objects.create(
                post=self.object,
                image=image,
                caption=caption,
                order=i + self.object.blogimage_set.count()
            )
        messages.success(self.request, 'Blog post updated successfully!')
        return response

    def test_func(self):
        post = self.get_object()
        return self.request.user == post.author

class BlogDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = BlogPost
    template_name = 'core/blog_confirm_delete.html'
    success_url = '/'

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        success_url = self.get_success_url()

        # Get API token from session
        api_token = request.session.get('api_token')
        
        # Delete from API first
        api_response, status_code = APIClient.delete_blog(
            self.object.id,
            api_token
        )

        if status_code not in [200, 204]:
            messages.error(request, 'Failed to delete post from remote server. Please try again.')
            return redirect('blog_detail', slug=self.object.slug)

        # If API deletion successful, delete from local database
        self.object.delete()
        messages.success(request, 'Blog post deleted successfully!')
        return redirect(success_url)

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
        try:
            data = json.loads(request.body)
            form = CommentForm({'content': data.get('content')})
            if form.is_valid():
                comment = form.save(commit=False)
                comment.post = post
                comment.author = request.user
                parent_id = data.get('parent_id')
                if parent_id:
                    parent_comment = Comment.objects.get(id=parent_id)
                    comment.parent = parent_comment
                
                comment.save()
                return JsonResponse({
                    'status': 'success',
                    'comment_id': comment.id,
                    'author': request.user.username,
                    'content': comment.content,
                    'created_at': comment.created_at.strftime('%b %d, %Y %H:%M'),
                    'parent_id': parent_id
                })
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON data'}, status=400)
        except Comment.DoesNotExist:
            return JsonResponse({'error': 'Parent comment not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
                
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
            # Update Django profile
            profile = form.save()
            
            # Sync with Flask API
            api_response, status_code = APIClient.update_user_profile(
                request.api_token,
                bio=profile.bio,
                profile_pic=profile.avatar.url if profile.avatar else None
            )
            
            if status_code == 200:
                messages.success(request, 'Profile updated successfully!')
            else:
                messages.warning(request, 'Profile updated in Django but API sync failed')
            return redirect('profile')
    else:
        form = UserProfileForm(instance=profile)
        
        # Get API profile data
        api_response, status_code = APIClient.get_user_profile(request.api_token)
        if status_code == 200:
            # Update local profile with API data if needed
            if api_response.get('bio') and not profile.bio:
                profile.bio = api_response['bio']
                profile.save()
    
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
