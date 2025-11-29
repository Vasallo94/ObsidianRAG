"""Service for tracking file metadata and detecting changes for incremental indexing"""
import json
import os
from datetime import datetime
from typing import Dict, Set, Tuple
import logging

logger = logging.getLogger(__name__)


class FileMetadataTracker:
    """Tracks file metadata to detect changes for incremental indexing"""
    
    def __init__(self, metadata_file: str = "metadata.json"):
        self.metadata_file = metadata_file
        self.metadata: Dict[str, dict] = {}
        self._load_metadata()
    
    def _load_metadata(self):
        """Load existing metadata from file"""
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, 'r') as f:
                    self.metadata = json.load(f)
                logger.info(f"Loaded metadata for {len(self.metadata)} files")
            except Exception as e:
                logger.warning(f"Could not load metadata file: {e}")
                self.metadata = {}
        else:
            logger.info("No existing metadata file found, starting fresh")
            self.metadata = {}
    
    def _save_metadata(self):
        """Save metadata to file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.metadata_file) or ".", exist_ok=True)
            
            with open(self.metadata_file, 'w') as f:
                json.dump(self.metadata, f, indent=2)
            logger.info(f"Saved metadata for {len(self.metadata)} files")
        except Exception as e:
            logger.error(f"Could not save metadata file: {e}")
    
    def get_current_files(self, obsidian_path: str) -> Dict[str, dict]:
        """
        Get current state of all .md files in obsidian vault
        
        Returns:
            Dict mapping filepath to metadata (mtime, size, etc.)
        """
        current_files = {}
        
        for root, _, files in os.walk(obsidian_path):
            for file in files:
                if file.endswith('.md'):
                    filepath = os.path.join(root, file)
                    try:
                        stat = os.stat(filepath)
                        current_files[filepath] = {
                            'mtime': stat.st_mtime,
                            'size': stat.st_size,
                            'last_indexed': datetime.now().isoformat()
                        }
                    except Exception as e:
                        logger.warning(f"Could not stat file {filepath}: {e}")
        
        return current_files
    
    def detect_changes(self, obsidian_path: str) -> Tuple[Set[str], Set[str], Set[str]]:
        """
        Detect which files are new, modified, or deleted
        
        Returns:
            Tuple of (new_files, modified_files, deleted_files)
        """
        current_files = self.get_current_files(obsidian_path)
        old_files = set(self.metadata.keys())
        current_file_set = set(current_files.keys())
        
        # Detect new files
        new_files = current_file_set - old_files
        
        # Detect deleted files
        deleted_files = old_files - current_file_set
        
        # Detect modified files (exist in both but mtime changed)
        modified_files = set()
        for filepath in (old_files & current_file_set):
            old_mtime = self.metadata[filepath].get('mtime', 0)
            new_mtime = current_files[filepath]['mtime']
            
            if new_mtime > old_mtime:
                modified_files.add(filepath)
        
        logger.info(
            f"Changes detected: {len(new_files)} new, "
            f"{len(modified_files)} modified, {len(deleted_files)} deleted"
        )
        
        return new_files, modified_files, deleted_files
    
    def update_metadata(self, obsidian_path: str):
        """Update metadata to current state"""
        self.metadata = self.get_current_files(obsidian_path)
        self._save_metadata()
    
    def remove_files(self, filepaths: Set[str]):
        """Remove files from metadata"""
        for filepath in filepaths:
            self.metadata.pop(filepath, None)
        self._save_metadata()
    
    def should_rebuild(self, obsidian_path: str, threshold: float = 0.3) -> bool:
        """
        Determine if a full rebuild is better than incremental update
        
        Args:
            threshold: If more than this fraction of files changed, recommend rebuild
        
        Returns:
            True if should do full rebuild instead of incremental
        """
        new_files, modified_files, deleted_files = self.detect_changes(obsidian_path)
        
        total_changes = len(new_files) + len(modified_files) + len(deleted_files)
        total_files = len(self.get_current_files(obsidian_path))
        
        if total_files == 0:
            return True
        
        change_ratio = total_changes / total_files
        
        logger.info(f"Change ratio: {change_ratio:.2%} (threshold: {threshold:.2%})")
        
        return change_ratio > threshold
