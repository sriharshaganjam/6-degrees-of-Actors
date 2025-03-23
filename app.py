import streamlit as st
import networkx as nx
import requests
import time
import matplotlib.pyplot as plt
import os

# Set page config must be the first streamlit command
st.set_page_config(
    page_title="Actor Connection Finder",
    page_icon="🎬",
    layout="wide"
)

# Hardcoded API key (for development only)
TMDB_API_KEY = "b91a0fbde9fc501f2b98a260f47ccceb"  # Replace with your actual TMDB API key
# API base URL
BASE_URL = "https://api.tmdb.org/3"

# App title and description
st.title("🎬 Six Degrees of Hollywood")
st.subheader("Find connections between actors through their movie collaborations")

# Cache API requests to improve performance
@st.cache_data(ttl=3600)
def search_actor(name):
    """Search for an actor by name and return their ID and profile info"""
    url = f"{BASE_URL}/search/person"
    params = {
        "api_key": TMDB_API_KEY,
        "query": name,
        "language": "en-US",
        "include_adult": False
    }
    response = requests.get(url, params=params)
    data = response.json()
    
    if data["total_results"] > 0:
        return data["results"][0]
    return None

@st.cache_data(ttl=3600)
def get_actor_movies(actor_id):
    """Get movies an actor has appeared in"""
    url = f"{BASE_URL}/person/{actor_id}/movie_credits"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "en-US"
    }
    response = requests.get(url, params=params)
    data = response.json()
    
    # Filter for cast only (not crew)
    return data.get("cast", [])

@st.cache_data(ttl=3600)
def get_movie_cast(movie_id):
    """Get the cast of a movie"""
    url = f"{BASE_URL}/movie/{movie_id}/credits"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "en-US"
    }
    response = requests.get(url, params=params)
    data = response.json()
    
    return data.get("cast", [])

@st.cache_data(ttl=3600)
def get_movie_details(movie_id):
    """Get details about a movie"""
    url = f"{BASE_URL}/movie/{movie_id}"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "en-US"
    }
    response = requests.get(url, params=params)
    return response.json()

def build_actor_graph(start_actor_id, max_depth=2, max_movies_per_actor=5):
    """Build a graph of connected actors starting from a given actor"""
    G = nx.Graph()
    visited_actors = set()
    visited_movies = set()
    
    # Add starting actor to graph
    actor_movies = get_actor_movies(start_actor_id)
    start_actor_data = None
    for movie in actor_movies:
        if not start_actor_data and movie.get("cast"):
            for cast_member in movie.get("cast", []):
                if cast_member["id"] == start_actor_id:
                    start_actor_data = cast_member
                    break
    
    # If we still don't have the actor data, use a placeholder
    if not start_actor_data:
        start_actor_data = {"id": start_actor_id, "name": f"Actor {start_actor_id}", "profile_path": None}
    
    # Add starting actor to the graph
    profile_path = start_actor_data.get("profile_path")
    image_url = f"https://image.tmdb.org/t/p/w185{profile_path}" if profile_path else ""
    G.add_node(start_actor_id, name=start_actor_data.get("name", f"Actor {start_actor_id}"), image=image_url)
    
    # Queue for BFS traversal: (actor_id, depth)
    queue = [(start_actor_id, 0)]
    
    with st.spinner("Building actor network..."):
        while queue:
            actor_id, depth = queue.pop(0)
            
            if actor_id in visited_actors:
                continue
                
            visited_actors.add(actor_id)
            
            # Stop if we've reached max depth
            if depth >= max_depth:
                continue
            
            # Get actor's movies
            movies = get_actor_movies(actor_id)
            
            # Sort by popularity and take top N
            movies = sorted(movies, key=lambda x: x.get("popularity", 0), reverse=True)[:max_movies_per_actor]
            
            for movie in movies:
                movie_id = movie["id"]
                movie_title = movie["title"]
                
                if movie_id in visited_movies:
                    continue
                    
                visited_movies.add(movie_id)
                
                # Get cast of the movie
                cast = get_movie_cast(movie_id)
                
                # Add edges between actors in this movie
                for cast_member in cast[:10]:  # Limit to top 10 cast members
                    cast_id = cast_member["id"]
                    cast_name = cast_member["name"]
                    
                    # Add actor node if not already in graph
                    if not G.has_node(cast_id):
                        profile_path = cast_member.get("profile_path")
                        image_url = f"https://image.tmdb.org/t/p/w185{profile_path}" if profile_path else ""
                        G.add_node(cast_id, name=cast_name, image=image_url)
                    
                    # Add edge with movie as relationship
                    if actor_id != cast_id:
                        if G.has_edge(actor_id, cast_id):
                            # Update edge with new movie
                            G[actor_id][cast_id]["movies"].append(movie_title)
                        else:
                            G.add_edge(actor_id, cast_id, movies=[movie_title])
                    
                    # Add new actors to queue
                    if cast_id not in visited_actors:
                        queue.append((cast_id, depth + 1))
    
    return G

def find_actor_connection(actor1_id, actor2_id):
    """Find the shortest path connecting two actors"""
    # Build graph starting from the first actor
    G = build_actor_graph(actor1_id, max_depth=2, max_movies_per_actor=5)
    
    # First check if second actor is in the graph
    if actor2_id not in G:
        # If not, build a graph from the second actor
        G2 = build_actor_graph(actor2_id, max_depth=2, max_movies_per_actor=5)
        
        # Merge the graphs
        G = nx.compose(G, G2)
        
        # Find common movies between actors in both parts of the graph
        st.info(f"Building bridge connections between the actor networks...")
        
        # Get potential bridge actors (from first graph)
        actor1_neighbors = set(G.neighbors(actor1_id))
        # Get potential bridge actors (from second graph)
        actor2_neighbors = set(G.neighbors(actor2_id))
        
        # Try to find connections between these two neighborhoods
        bridges_created = 0
        for a1 in list(actor1_neighbors)[:10]:  # Limit to 10 neighbors
            movies1 = get_actor_movies(a1)
            movie_ids1 = {m["id"] for m in movies1[:10]}  # Top 10 movies
            
            for a2 in list(actor2_neighbors)[:10]:  # Limit to 10 neighbors
                movies2 = get_actor_movies(a2)
                movie_ids2 = {m["id"] for m in movies2[:10]}  # Top 10 movies
                
                # Find common movies
                common_movies = movie_ids1.intersection(movie_ids2)
                
                for movie_id in common_movies:
                    # Get movie details
                    movie_details = get_movie_details(movie_id)
                    movie_title = movie_details.get("title", f"Movie {movie_id}")
                    
                    # Add direct connections
                    if not G.has_edge(a1, a2):
                        G.add_edge(a1, a2, movies=[movie_title])
                        bridges_created += 1
                
                # Limit the number of bridges we create
                if bridges_created >= 20:
                    break
            
            if bridges_created >= 20:
                break
        
        st.info(f"Created {bridges_created} bridge connections between the networks.")
    
    # Find shortest path if it exists
    try:
        if actor1_id in G and actor2_id in G:
            path = nx.shortest_path(G, actor1_id, actor2_id)
            return G, path
        else:
            return G, None
    except nx.NetworkXNoPath:
        return G, None

def visualize_path_simple(G, path):
    """Create a simple visualization of the connection path using matplotlib"""
    if path:
        # Create a subgraph with just the path
        path_edges = [(path[i], path[i+1]) for i in range(len(path)-1)]
        H = nx.Graph()
        
        # Add nodes and edges
        for i, node in enumerate(path):
            H.add_node(node, name=G.nodes[node]["name"])
        
        for i in range(len(path)-1):
            H.add_edge(path[i], path[i+1])
        
        # Create the plot
        plt.figure(figsize=(10, 6))
        pos = nx.spring_layout(H, seed=42)  # For consistent layout
        
        # Draw the network
        nx.draw(H, pos, with_labels=False, node_color='skyblue', 
                node_size=1500, edge_color='gray', linewidths=2, font_size=10)
        
        # Add labels with actor names
        labels = {node: G.nodes[node]["name"] for node in H.nodes()}
        nx.draw_networkx_labels(H, pos, labels=labels)
        
        # Add edge labels with movie names
        edge_labels = {}
        for i in range(len(path)-1):
            edge_labels[(path[i], path[i+1])] = G[path[i]][path[i+1]]["movies"][0]
        
        nx.draw_networkx_edge_labels(H, pos, edge_labels=edge_labels, font_size=8)
        
        # Remove axis
        plt.axis('off')
        
        # Return the figure
        return plt
    return None

# User interface
with st.container():
    col1, col2 = st.columns(2)
    
    with col1:
        actor1_name = st.text_input("Enter first actor's name", "Tom Hanks")
    
    with col2:
        actor2_name = st.text_input("Enter second actor's name", "Kevin Bacon")

if st.button("Find Connection"):
    # Search for actors
    actor1 = search_actor(actor1_name)
    actor2 = search_actor(actor2_name)
    
    if not actor1:
        st.error(f"Could not find actor: {actor1_name}")
    elif not actor2:
        st.error(f"Could not find actor: {actor2_name}")
    else:
        # Display found actors
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader(actor1["name"])
            if actor1.get("profile_path"):
                st.image(f"https://image.tmdb.org/t/p/w185{actor1['profile_path']}")
        
        with col2:
            st.subheader(actor2["name"])
            if actor2.get("profile_path"):
                st.image(f"https://image.tmdb.org/t/p/w185{actor2['profile_path']}")
        
        # Find connection
        with st.spinner("Finding connection..."):
            G, path = find_actor_connection(actor1["id"], actor2["id"])
        
        if path:
            st.success(f"Found a connection with {len(path)-1} degrees of separation!")
            
            # Display path as text
            st.subheader("Connection Path:")
            
            for i in range(len(path)-1):
                current_actor = G.nodes[path[i]]["name"]
                next_actor = G.nodes[path[i+1]]["name"]
                movies = G[path[i]][path[i+1]]["movies"]
                
                st.write(f"{current_actor} → {next_actor} via '{movies[0]}'")
            
            # Display simple visualization
            st.subheader("Connection Visualization:")
            plt_fig = visualize_path_simple(G, path)
            if plt_fig:
                st.pyplot(plt_fig)
        else:
            st.error(f"No connection found between {actor1['name']} and {actor2['name']} within the search depth.")
            st.info("Try increasing the search depth or choose different actors.")
            
            # Display stats about the graph
            st.write(f"Searched through {len(G.nodes)} actors and {len(G.edges)} connections.")

# Sidebar with additional information and settings
with st.sidebar:
    st.header("About")
    st.markdown("""
    This app uses data from The Movie Database (TMDB) to find connections between actors through their movie collaborations.
    
    The "six degrees of separation" theory suggests that any two actors can be connected through no more than six links.
    
    ### How it works:
    1. Enter two actor names
    2. The app searches for movies they've appeared in
    3. It builds a network of actors and their connections
    4. It finds the shortest path between the two actors
    
    ### Note:
    - The search is limited to a depth of 2 to keep the response time reasonable
    - Only the top 5 most popular movies per actor are considered
    """)
    
    st.header("Sample Connections")
    st.markdown("""
    Try these pairs:
    - Tom Hanks → Kevin Bacon
    - Meryl Streep → Brad Pitt  
    - Leonardo DiCaprio → Emma Stone
    """)
