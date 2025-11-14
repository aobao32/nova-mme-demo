#!/usr/bin/env python3
"""
Nova MME Image Search GUI
A macOS native-style GUI for searching images using text queries
"""

# brew install python-tk@3.13

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import boto3
import json
import base64
from io import BytesIO
from PIL import Image, ImageTk
import threading
from typing import List, Dict, Any

# Try to import mousewheel support for better scrolling on macOS
try:
    import tkintermousewheel
except ImportError:
    tkintermousewheel = None


class NovaImageSearchGUI:
    # Model configurations
    MODELS = {
        'amazon.nova-2-multimodal-embeddings-v1:0': {
            'dimension': 3072,
            'index': 'my-image-index-02-lambda'
        },
        'twelvelabs.marengo-embed-3-0-v1:0': {
            'dimension': 512,
            'index': 'my-image-index-03-tme3'
        }
    }
    
    def __init__(self, root):
        self.root = root
        self.root.title("Nova MME Image Search")
        
        # Default configuration
        self.default_region = 'us-east-1'
        self.default_bucket = 'my-nova-mme-demo-01'
        self.default_model = 'amazon.nova-2-multimodal-embeddings-v1:0'
        self.embedding_dimension = self.MODELS[self.default_model]['dimension']
        
        # Thumbnail size
        self.thumbnail_size = (360, 240)
        
        # AWS clients (will be initialized on query)
        self.bedrock_client = None
        self.s3vectors_client = None
        self.s3_client = None
        
        # Results storage
        self.current_results = []
        self.image_labels = []
        self.results_container = None
        
        # Setup UI
        self.setup_ui()
        
        # Set window size and position after UI is created
        self.root.update_idletasks()
        self.root.geometry("1200x900+0+0")
    
    def setup_ui(self):
        """Setup the user interface"""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Title
        title_label = ttk.Label(
            main_frame, 
            text="Nova MME Image Search", 
            font=('Helvetica', 20, 'bold')
        )
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20))
        
        # Configuration section
        config_frame = ttk.LabelFrame(main_frame, text="Configuration", padding="10")
        config_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        config_frame.columnconfigure(1, weight=1)
        
        row = 0
        
        # Region
        ttk.Label(config_frame, text="Region:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.region_var = tk.StringVar(value=self.default_region)
        region_entry = ttk.Entry(config_frame, textvariable=self.region_var, width=30)
        region_entry.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        row += 1
        
        # Vector Bucket
        ttk.Label(config_frame, text="Vector Bucket:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.bucket_var = tk.StringVar(value=self.default_bucket)
        bucket_entry = ttk.Entry(config_frame, textvariable=self.bucket_var, width=30)
        bucket_entry.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        row += 1
        
        # Model ID (Dropdown)
        ttk.Label(config_frame, text="Model:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.model_var = tk.StringVar(value=self.default_model)
        model_combo = ttk.Combobox(
            config_frame,
            textvariable=self.model_var,
            values=list(self.MODELS.keys()),
            state="readonly",
            width=40
        )
        model_combo.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        model_combo.bind('<<ComboboxSelected>>', self.on_model_changed)
        row += 1
        
        # Index Name (auto-updated based on model)
        ttk.Label(config_frame, text="Index Name:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.index_var = tk.StringVar(value=self.MODELS[self.default_model]['index'])
        index_entry = ttk.Entry(config_frame, textvariable=self.index_var, width=30)
        index_entry.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        row += 1
        
        # Top K
        ttk.Label(config_frame, text="Top K Results:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.topk_var = tk.StringVar(value="5")
        topk_combo = ttk.Combobox(
            config_frame, 
            textvariable=self.topk_var, 
            values=["5", "10"],
            state="readonly",
            width=10
        )
        topk_combo.grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        row += 1
        
        # Distance Threshold
        ttk.Label(config_frame, text="Distance Threshold:").grid(row=row, column=0, sticky=tk.W, pady=5)
        threshold_frame = ttk.Frame(config_frame)
        threshold_frame.grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        
        self.threshold_var = tk.StringVar(value="0.8")
        threshold_entry = ttk.Entry(threshold_frame, textvariable=self.threshold_var, width=10)
        threshold_entry.pack(side=tk.LEFT)
        
        ttk.Label(
            threshold_frame, 
            text="(0.0-1.0, lower = more similar)", 
            font=('Helvetica', 9), 
            foreground='gray'
        ).pack(side=tk.LEFT, padx=(5, 0))
        
        # Query section
        query_frame = ttk.LabelFrame(main_frame, text="Search Query", padding="10")
        query_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        query_frame.columnconfigure(0, weight=1)
        
        # Query text
        ttk.Label(query_frame, text="Enter search text:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        self.query_var = tk.StringVar()
        query_entry = ttk.Entry(query_frame, textvariable=self.query_var, font=('Helvetica', 12))
        query_entry.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        query_entry.bind('<Return>', lambda e: self.search_images())
        
        # Search button
        self.search_button = ttk.Button(
            query_frame, 
            text="Search Images", 
            command=self.search_images,
            style='Accent.TButton'
        )
        self.search_button.grid(row=2, column=0, pady=(0, 5))
        
        # Status label
        self.status_var = tk.StringVar(value="Ready")
        status_label = ttk.Label(query_frame, textvariable=self.status_var, foreground='gray')
        status_label.grid(row=3, column=0)
        
        # Results section
        results_frame = ttk.LabelFrame(main_frame, text="Search Results", padding="10")
        results_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        main_frame.rowconfigure(3, weight=1)
        
        # Create canvas with scrollbar for results
        canvas = tk.Canvas(results_frame, bg='white')
        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=canvas.yview)
        self.results_container = ttk.Frame(canvas)
        
        self.results_container.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.results_container, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
        
        # Store canvas reference for mouse wheel binding
        self.results_canvas = canvas
        
        # Setup mouse wheel scrolling
        if tkintermousewheel:
            # Use tkintermousewheel for better macOS support
            tkintermousewheel.enable_mousewheel(canvas, self.results_container)
        else:
            # Fallback to manual binding
            canvas.bind("<MouseWheel>", self._on_canvas_mousewheel)
            canvas.bind("<Button-4>", self._on_canvas_mousewheel)
            canvas.bind("<Button-5>", self._on_canvas_mousewheel)
            self._bind_mousewheel_recursive(self.results_container)
        
        # Add keyboard shortcuts for scrolling
        self.root.bind("<Up>", lambda e: self._scroll_results(-3))
        self.root.bind("<Down>", lambda e: self._scroll_results(3))
        self.root.bind("<Prior>", lambda e: self._scroll_results(-10))  # Page Up
        self.root.bind("<Next>", lambda e: self._scroll_results(10))    # Page Down
    
    def _bind_mousewheel_recursive(self, widget):
        """Recursively bind mouse wheel events to widget and all children"""
        widget.bind("<MouseWheel>", self._on_canvas_mousewheel)
        widget.bind("<Button-4>", self._on_canvas_mousewheel)
        widget.bind("<Button-5>", self._on_canvas_mousewheel)
        
        # Recursively bind to all children
        for child in widget.winfo_children():
            self._bind_mousewheel_recursive(child)
    
    def _scroll_results(self, delta: int):
        """Scroll results canvas by delta units"""
        if self.results_canvas:
            self.results_canvas.yview_scroll(delta, "units")
    
    def _on_canvas_mousewheel(self, event):
        """Handle mouse wheel scrolling on canvas"""
        try:
            # macOS: event.delta (positive = up, negative = down)
            # Linux: event.num (4 = up, 5 = down)
            # Windows: event.delta (positive = up, negative = down)
            
            if hasattr(event, 'delta') and event.delta != 0:
                # macOS and Windows
                delta = -1 if event.delta > 0 else 1
            elif hasattr(event, 'num'):
                # Linux
                delta = -1 if event.num == 4 else 1
            else:
                return "break"
            
            self.results_canvas.yview_scroll(delta * 3, "units")
        except Exception:
            pass
        
        return "break"  # Prevent event propagation
    
    def on_model_changed(self, event=None):
        """Handle model selection change"""
        model_id = self.model_var.get()
        if model_id in self.MODELS:
            # Update index name and embedding dimension
            self.index_var.set(self.MODELS[model_id]['index'])
            self.embedding_dimension = self.MODELS[model_id]['dimension']
    
    def initialize_clients(self):
        """Initialize AWS clients with current region"""
        region = self.region_var.get()
        self.bedrock_client = boto3.client('bedrock-runtime', region_name=region)
        self.s3vectors_client = boto3.client('s3vectors', region_name=region)
        self.s3_client = boto3.client('s3', region_name=region)
    
    def generate_text_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using selected model"""
        model_id = self.model_var.get()
        
        if model_id == 'amazon.nova-2-multimodal-embeddings-v1:0':
            return self._generate_nova_embedding(text)
        elif model_id == 'twelvelabs.marengo-embed-3-0-v1:0':
            return self._generate_tme3_embedding(text)
        else:
            raise ValueError(f"Unknown model: {model_id}")
    
    def _generate_nova_embedding(self, text: str) -> List[float]:
        """Generate embedding using Amazon Nova MME"""
        model_input = {
            "taskType": "SINGLE_EMBEDDING",
            "singleEmbeddingParams": {
                "embeddingPurpose": "IMAGE_RETRIEVAL",
                "embeddingDimension": self.embedding_dimension,
                "text": {
                    "truncationMode": "END",
                    "value": text
                }
            }
        }
        
        response = self.bedrock_client.invoke_model(
            modelId=self.model_var.get(),
            body=json.dumps(model_input)
        )
        
        result = json.loads(response['body'].read())
        embedding = result.get('embeddings', [{}])[0].get('embedding', [])
        
        return embedding
    
    def _generate_tme3_embedding(self, text: str) -> List[float]:
        """Generate embedding using Twelve Labs Marengo Embed 3.0"""
        model_input = {
            "inputType": "text",
            "text": {
                "inputText": text
            }
        }
        
        response = self.bedrock_client.invoke_model(
            modelId=self.model_var.get(),
            body=json.dumps(model_input)
        )
        
        result = json.loads(response['body'].read())
        
        # Parse TME3 response format
        if isinstance(result, dict) and 'data' in result:
            data_list = result['data']
            if isinstance(data_list, list) and len(data_list) > 0:
                first_item = data_list[0]
                if isinstance(first_item, dict) and 'embedding' in first_item:
                    embedding = first_item['embedding']
                else:
                    raise ValueError(f"Unexpected data item format: {first_item}")
            else:
                raise ValueError("Empty data list in response")
        elif isinstance(result, dict) and 'embedding' in result:
            embedding_list = result['embedding']
            if isinstance(embedding_list, list) and len(embedding_list) > 0:
                first_item = embedding_list[0]
                if isinstance(first_item, dict) and 'embedding' in first_item:
                    embedding = first_item['embedding']
                elif isinstance(first_item, (int, float)):
                    embedding = embedding_list
                else:
                    raise ValueError(f"Unexpected embedding item format: {first_item}")
            else:
                embedding = embedding_list
        else:
            raise ValueError(f"Unexpected response format: {result}")
        
        return embedding
    
    def query_vectors(self, query_embedding: List[float]) -> List[Dict[str, Any]]:
        """Query S3 Vectors for similar vectors"""
        response = self.s3vectors_client.query_vectors(
            vectorBucketName=self.bucket_var.get(),
            indexName=self.index_var.get(),
            queryVector={'float32': query_embedding},
            topK=int(self.topk_var.get()),
            returnDistance=True,
            returnMetadata=True
        )
        
        return response.get('vectors', [])
    
    def load_image_from_s3(self, s3_uri: str, thumbnail_size=None) -> tuple:
        """Load image from S3 and create thumbnail"""
        if thumbnail_size is None:
            thumbnail_size = self.thumbnail_size
            
        # Parse S3 URI
        if s3_uri.startswith('s3://'):
            path = s3_uri[5:]
            parts = path.split('/', 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ''
        else:
            return None, None
        
        # Download image from S3
        response = self.s3_client.get_object(Bucket=bucket, Key=key)
        image_data = response['Body'].read()
        
        # Create PIL Image
        original_image = Image.open(BytesIO(image_data))
        
        # Create thumbnail
        thumbnail = original_image.copy()
        thumbnail.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)
        
        return original_image, thumbnail
    
    def show_full_image(self, original_image, title):
        """Show full-size image in a new window"""
        window = tk.Toplevel(self.root)
        window.title(title)
        
        # Convert to PhotoImage
        photo = ImageTk.PhotoImage(original_image)
        
        # Create label with image
        label = tk.Label(window, image=photo)
        label.image = photo  # Keep a reference
        label.pack()
    
    def calculate_columns(self):
        """Calculate number of columns based on window width"""
        # Get window width
        window_width = self.root.winfo_width()
        if window_width <= 1:
            window_width = 1200  # Default width
        
        # Calculate columns (thumbnail width + padding)
        # 360 (thumbnail) + 20 (padding left/right) + 20 (frame padding) = 400
        item_width = 400
        columns = max(2, window_width // item_width)  # At least 2 columns
        
        return columns
    
    def display_results(self, results: List[Dict[str, Any]]):
        """Display search results with images"""
        # Store results for potential re-layout
        self.current_results = results
        
        # Clear previous results
        for widget in self.results_container.winfo_children():
            widget.destroy()
        
        if not results:
            no_results = ttk.Label(
                self.results_container, 
                text="No results found", 
                font=('Helvetica', 14)
            )
            no_results.grid(row=0, column=0, pady=20)
            return
        
        # Filter results by distance threshold
        try:
            threshold = float(self.threshold_var.get())
        except ValueError:
            threshold = 0.8  # Default threshold
        
        filtered_results = []
        for result in results:
            distance = result.get('distance')
            if distance is not None and distance <= threshold:
                filtered_results.append(result)
        
        if not filtered_results:
            no_results = ttk.Label(
                self.results_container, 
                text=f"No results found within distance threshold {threshold}\n(Try increasing the threshold value)", 
                font=('Helvetica', 14),
                justify=tk.CENTER
            )
            no_results.grid(row=0, column=0, pady=20)
            return
        
        # Calculate columns based on window width
        columns = self.calculate_columns()
        
        # Display filtered results in a responsive grid
        for idx, result in enumerate(filtered_results):
            row = idx // columns
            col = idx % columns
            
            # Create frame for each result
            result_frame = ttk.Frame(self.results_container, relief='solid', borderwidth=1, padding=10)
            result_frame.grid(row=row, column=col, padx=10, pady=10, sticky=(tk.W, tk.E, tk.N, tk.S))
            
            # Extract metadata
            metadata = result.get('metadata', {})
            s3_uri = metadata.get('s3_uri') or metadata.get('full_path', '')
            distance = result.get('distance', 'N/A')
            
            # Result info
            info_text = f"Result {idx + 1}\nDistance: {distance:.4f}" if isinstance(distance, float) else f"Result {idx + 1}"
            info_label = ttk.Label(result_frame, text=info_text, font=('Helvetica', 12, 'bold'))
            info_label.grid(row=0, column=0, pady=(0, 5))
            
            # Load and display image
            try:
                original_image, thumbnail = self.load_image_from_s3(s3_uri)
                
                if thumbnail:
                    # Convert to PhotoImage
                    photo = ImageTk.PhotoImage(thumbnail)
                    
                    # Create clickable image label
                    image_label = tk.Label(result_frame, image=photo, cursor="hand2")
                    image_label.image = photo  # Keep a reference
                    image_label.grid(row=1, column=0, pady=(0, 5))
                    
                    # Bind click event to show full image
                    image_label.bind(
                        "<Button-1>", 
                        lambda e, img=original_image, uri=s3_uri: self.show_full_image(img, uri)
                    )
                else:
                    error_label = ttk.Label(result_frame, text="Failed to load image")
                    error_label.grid(row=1, column=0)
            
            except Exception as e:
                error_label = ttk.Label(result_frame, text=f"Error: {str(e)}")
                error_label.grid(row=1, column=0)
            
            # Display S3 URI
            uri_label = ttk.Label(
                result_frame, 
                text=s3_uri, 
                font=('Helvetica', 9),
                foreground='gray',
                wraplength=340
            )
            uri_label.grid(row=2, column=0, pady=(5, 0))
    
    def search_images_thread(self):
        """Search images in a separate thread"""
        try:
            # Update status
            self.status_var.set("Initializing AWS clients...")
            self.initialize_clients()
            
            # Get query text
            query_text = self.query_var.get().strip()
            if not query_text:
                messagebox.showwarning("Warning", "Please enter search text")
                self.status_var.set("Ready")
                self.search_button.config(state='normal')
                return
            
            # Generate embedding
            self.status_var.set(f"Generating embedding for: '{query_text}'...")
            embedding = self.generate_text_embedding(query_text)
            
            # Query vectors
            self.status_var.set("Searching for similar images...")
            results = self.query_vectors(embedding)
            
            # Display results
            self.status_var.set(f"Found {len(results)} results. Loading images...")
            self.display_results(results)
            
            # Update status
            self.status_var.set(f"✓ Search completed! Found {len(results)} results")
            
        except Exception as e:
            messagebox.showerror("Error", f"Search failed: {str(e)}")
            self.status_var.set("Error occurred")
        
        finally:
            self.search_button.config(state='normal')
    
    def search_images(self):
        """Start image search"""
        # Disable search button
        self.search_button.config(state='disabled')
        
        # Run search in separate thread to avoid blocking UI
        thread = threading.Thread(target=self.search_images_thread, daemon=True)
        thread.start()


def main():
    """Main function to run the GUI"""
    root = tk.Tk()
    
    # Set macOS native look
    try:
        root.tk.call('tk', 'scaling', 2.0)  # For Retina displays
    except:
        pass
    
    app = NovaImageSearchGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
