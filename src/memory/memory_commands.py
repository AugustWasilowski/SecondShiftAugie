"""
Discord slash commands for memory management.

This module implements Discord slash commands that allow users to interact with
the memory system, including viewing, searching, exporting, and deleting memories.

Requirements addressed:
- 3.1: /mem show command with pagination and user filtering
- 3.2: /mem find command with vector search and result formatting
- 3.3: /mem export command with JSON generation and DM delivery
- 3.4: /mem forget command with memory ID validation
- 3.5: /forgetme command with complete user data deletion
"""

import logging
import os
from typing import TYPE_CHECKING, Optional, List
from pathlib import Path

import nextcord
from nextcord.ext import commands

if TYPE_CHECKING:
    from .memory_service import MemoryService

from .models import ThreadCtx, MemoryHit

logger = logging.getLogger(__name__)


class MemoryCommands:
    """Discord command handlers for memory operations."""
    
    def __init__(self, bot: commands.Bot, memory_service: "MemoryService"):
        """
        Initialize memory command handlers.
        
        Args:
            bot: Discord bot instance
            memory_service: Memory service instance
        """
        self.bot = bot
        self.memory_service = memory_service
        self._commands_registered = False
        
        logger.info("MemoryCommands initialized")
    
    def register_commands(self) -> None:
        """Register all memory-related slash commands with the Discord bot."""
        if self._commands_registered:
            logger.warning("Memory commands already registered")
            return
        
        try:
            # Register each memory command
            self._register_mem_show_command()
            self._register_mem_find_command()
            self._register_mem_export_command()
            self._register_mem_forget_command()
            self._register_forgetme_command()
            
            self._commands_registered = True
            logger.info("All memory commands registered successfully")
            
        except Exception as e:
            logger.error(f"Error registering memory commands: {e}")
            raise
    
    def _register_mem_show_command(self) -> None:
        """
        Register the /mem show slash command.
        
        Requirement 3.1: WHEN a user executes "/mem show" THEN the system SHALL display their latest memories with metadata
        """
        @self.bot.slash_command(
            name="mem-show",
            description="Show your latest memories with metadata"
        )
        async def mem_show(
            interaction: nextcord.Interaction,
            user: Optional[nextcord.Member] = nextcord.SlashOption(
                description="Show memories for specific user (admin only)",
                required=False
            ),
            count: int = nextcord.SlashOption(
                description="Number of memories to show (default: 20, max: 50)",
                default=20,
                min_value=1,
                max_value=50
            )
        ):
            """Handle /mem-show slash command."""
            await self.handle_mem_show(interaction, user, count)
    
    def _register_mem_find_command(self) -> None:
        """
        Register the /mem find slash command.
        
        Requirement 3.2: WHEN a user executes "/mem find <query>" THEN the system SHALL perform vector search and return relevant memories
        """
        @self.bot.slash_command(
            name="mem-find",
            description="Search your memories using vector similarity"
        )
        async def mem_find(
            interaction: nextcord.Interaction,
            query: str = nextcord.SlashOption(
                description="Search query for finding relevant memories",
                min_length=3,
                max_length=200
            )
        ):
            """Handle /mem-find slash command."""
            await self.handle_mem_find(interaction, query)
    
    def _register_mem_export_command(self) -> None:
        """
        Register the /mem export slash command.
        
        Requirement 3.3: WHEN a user executes "/mem export" THEN the system SHALL generate a JSON export of their memories and DM it to them
        """
        @self.bot.slash_command(
            name="mem-export",
            description="Export your memories to a JSON file (sent via DM)"
        )
        async def mem_export(
            interaction: nextcord.Interaction,
            user: Optional[nextcord.Member] = nextcord.SlashOption(
                description="Export memories for specific user (admin only)",
                required=False
            )
        ):
            """Handle /mem-export slash command."""
            await self.handle_mem_export(interaction, user)
    
    def _register_mem_forget_command(self) -> None:
        """
        Register the /mem forget slash command.
        
        Requirement 3.4: WHEN a user executes "/mem forget <id>" THEN the system SHALL delete the specified memory by ID
        """
        @self.bot.slash_command(
            name="mem-forget",
            description="Delete a specific memory by its ID"
        )
        async def mem_forget(
            interaction: nextcord.Interaction,
            memory_id: str = nextcord.SlashOption(
                description="UUID of the memory to delete",
                min_length=36,
                max_length=36
            )
        ):
            """Handle /mem-forget slash command."""
            await self.handle_mem_forget(interaction, memory_id)
    
    def _register_forgetme_command(self) -> None:
        """
        Register the /forgetme slash command.
        
        Requirement 3.5: WHEN a user executes "/forgetme" THEN the system SHALL hard-delete all of their LTM and summaries
        """
        @self.bot.slash_command(
            name="forgetme",
            description="⚠️ PERMANENTLY delete ALL your memories and conversation history"
        )
        async def forgetme(interaction: nextcord.Interaction):
            """Handle /forgetme slash command."""
            await self.handle_forgetme(interaction)
    
    async def handle_mem_show(
        self, 
        interaction: nextcord.Interaction, 
        user: Optional[nextcord.Member] = None, 
        count: int = 20
    ) -> None:
        """
        Handle /mem show slash command interaction.
        
        Args:
            interaction: Discord slash command interaction
            user: Optional user to show memories for (admin only)
            count: Number of memories to show
        """
        try:
            await interaction.response.defer()
            
            # Check if memory service is available
            if not self.memory_service.supports_ltm():
                await interaction.followup.send(
                    "❌ Memory system is not available or running in limited mode.",
                    ephemeral=True
                )
                return
            
            # Determine target user
            target_user = user if user else interaction.user
            
            # Check permissions for viewing other users' memories
            if user and user != interaction.user:
                if not self._is_admin(interaction.user):
                    await interaction.followup.send(
                        "❌ You don't have permission to view other users' memories.",
                        ephemeral=True
                    )
                    return
            
            # Create thread context
            ctx = ThreadCtx(
                guild_id=str(interaction.guild.id),
                channel_id=str(interaction.channel.id),
                user_id=str(target_user.id)
            )
            
            # Get recent memories using a broad search
            memories = await self.memory_service.retrieve(ctx, "recent memories", k=count)
            
            if not memories:
                user_mention = target_user.mention if target_user != interaction.user else "You"
                await interaction.followup.send(
                    f"📭 {user_mention} have no stored memories yet.",
                    ephemeral=True
                )
                return
            
            # Create paginated embed display
            embeds = self._create_memory_list_embeds(memories, target_user, count)
            
            if len(embeds) == 1:
                await interaction.followup.send(embed=embeds[0])
            else:
                # Send first embed with pagination buttons
                view = MemoryPaginationView(embeds)
                await interaction.followup.send(embed=embeds[0], view=view)
            
        except Exception as e:
            logger.error(f"Error in /mem show command: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while retrieving memories.",
                    ephemeral=True
                )
            except Exception as followup_error:
                logger.error(f"Error sending error response for /mem show: {followup_error}")
    
    async def handle_mem_find(self, interaction: nextcord.Interaction, query: str) -> None:
        """
        Handle /mem find slash command interaction.
        
        Args:
            interaction: Discord slash command interaction
            query: Search query for finding memories
        """
        try:
            await interaction.response.defer()
            
            # Check if memory service is available
            if not self.memory_service.supports_ltm():
                await interaction.followup.send(
                    "❌ Memory search is not available or running in limited mode.",
                    ephemeral=True
                )
                return
            
            # Create thread context
            ctx = ThreadCtx(
                guild_id=str(interaction.guild.id),
                channel_id=str(interaction.channel.id),
                user_id=str(interaction.user.id)
            )
            
            # Perform vector search
            memories = await self.memory_service.retrieve(ctx, query, k=10)
            
            if not memories:
                await interaction.followup.send(
                    f"🔍 No memories found matching: `{query}`",
                    ephemeral=True
                )
                return
            
            # Create search results embed
            embed = self._create_search_results_embed(memories, query)
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in /mem find command: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while searching memories.",
                    ephemeral=True
                )
            except Exception as followup_error:
                logger.error(f"Error sending error response for /mem find: {followup_error}")
    
    async def handle_mem_export(
        self, 
        interaction: nextcord.Interaction, 
        user: Optional[nextcord.Member] = None
    ) -> None:
        """
        Handle /mem export slash command interaction.
        
        Args:
            interaction: Discord slash command interaction
            user: Optional user to export memories for (admin only)
        """
        try:
            await interaction.response.defer()
            
            # Check if memory service is available
            if not self.memory_service.supports_ltm():
                await interaction.followup.send(
                    "❌ Memory export is not available or running in limited mode.",
                    ephemeral=True
                )
                return
            
            # Determine target user
            target_user = user if user else interaction.user
            
            # Check permissions for exporting other users' memories
            if user and user != interaction.user:
                if not self._is_admin(interaction.user):
                    await interaction.followup.send(
                        "❌ You don't have permission to export other users' memories.",
                        ephemeral=True
                    )
                    return
            
            # Export memories
            try:
                export_path = await self.memory_service.export_user_memories(
                    str(target_user.id), 
                    str(interaction.guild.id)
                )
                
                # Send file via DM
                try:
                    dm_channel = await target_user.create_dm()
                    
                    with open(export_path, 'rb') as f:
                        file = nextcord.File(f, filename=os.path.basename(export_path))
                        
                        embed = nextcord.Embed(
                            title="📦 Memory Export",
                            description=f"Your memory export from **{interaction.guild.name}**",
                            color=0x00ff00
                        )
                        embed.add_field(
                            name="Export Details",
                            value=f"Guild: {interaction.guild.name}\nRequested by: {interaction.user.mention}",
                            inline=False
                        )
                        embed.set_footer(text="This file contains all your stored memories in JSON format")
                        
                        await dm_channel.send(embed=embed, file=file)
                    
                    # Confirm in channel
                    user_mention = target_user.mention if target_user != interaction.user else "You"
                    await interaction.followup.send(
                        f"✅ {user_mention} memory export has been sent via DM.",
                        ephemeral=True
                    )
                    
                except nextcord.Forbidden:
                    # Fallback: offer to save to export directory
                    await interaction.followup.send(
                        f"⚠️ Could not send DM. Export saved to: `{export_path}`\n"
                        "Please contact an administrator to retrieve your export file.",
                        ephemeral=True
                    )
                    
            except Exception as export_error:
                logger.error(f"Memory export failed: {export_error}")
                await interaction.followup.send(
                    "❌ Failed to export memories. Please try again later.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error in /mem export command: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while exporting memories.",
                    ephemeral=True
                )
            except Exception as followup_error:
                logger.error(f"Error sending error response for /mem export: {followup_error}")
    
    async def handle_mem_forget(self, interaction: nextcord.Interaction, memory_id: str) -> None:
        """
        Handle /mem forget slash command interaction.
        
        Args:
            interaction: Discord slash command interaction
            memory_id: UUID of the memory to delete
        """
        try:
            await interaction.response.defer()
            
            # Check if memory service is available
            if not self.memory_service.supports_ltm():
                await interaction.followup.send(
                    "❌ Memory deletion is not available or running in limited mode.",
                    ephemeral=True
                )
                return
            
            # Validate UUID format
            if not self._is_valid_uuid(memory_id):
                await interaction.followup.send(
                    "❌ Invalid memory ID format. Please provide a valid UUID.",
                    ephemeral=True
                )
                return
            
            # Attempt to delete the memory
            try:
                deleted = await self.memory_service.forget_memory(memory_id)
                
                if deleted:
                    await interaction.followup.send(
                        f"✅ Memory `{memory_id}` has been deleted.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"❌ Memory `{memory_id}` not found or you don't have permission to delete it.",
                        ephemeral=True
                    )
                    
            except Exception as delete_error:
                logger.error(f"Memory deletion failed: {delete_error}")
                await interaction.followup.send(
                    "❌ Failed to delete memory. Please try again later.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error in /mem forget command: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while deleting the memory.",
                    ephemeral=True
                )
            except Exception as followup_error:
                logger.error(f"Error sending error response for /mem forget: {followup_error}")
    
    async def handle_forgetme(self, interaction: nextcord.Interaction) -> None:
        """
        Handle /forgetme slash command interaction.
        
        Args:
            interaction: Discord slash command interaction
        """
        try:
            # Create confirmation view
            view = ForgetMeConfirmationView()
            
            embed = nextcord.Embed(
                title="⚠️ Permanent Data Deletion",
                description=(
                    "**This action will PERMANENTLY delete ALL of your:**\n"
                    "• Stored memories and facts\n"
                    "• Conversation summaries\n"
                    "• Message history\n\n"
                    "**This cannot be undone!**"
                ),
                color=0xff0000
            )
            embed.add_field(
                name="What happens next?",
                value=(
                    "• All your data in this server will be deleted\n"
                    "• You can continue using the bot normally\n"
                    "• New memories will be created from future conversations"
                ),
                inline=False
            )
            embed.set_footer(text="Click 'Confirm Deletion' only if you're absolutely sure")
            
            await interaction.response.send_message(
                embed=embed, 
                view=view, 
                ephemeral=True
            )
            
            # Wait for user confirmation
            await view.wait()
            
            if view.confirmed:
                await self._perform_hard_delete(interaction)
            elif view.cancelled:
                embed.color = 0x00ff00
                embed.title = "✅ Deletion Cancelled"
                embed.description = "Your memories are safe. No data was deleted."
                embed.clear_fields()
                
                await interaction.edit_original_response(embed=embed, view=None)
            # If timeout, the view will handle it
                
        except Exception as e:
            logger.error(f"Error in /forgetme command: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while processing the deletion request.",
                    ephemeral=True
                )
            except Exception as followup_error:
                logger.error(f"Error sending error response for /forgetme: {followup_error}")
    
    async def _perform_hard_delete(self, interaction: nextcord.Interaction) -> None:
        """
        Perform the actual hard deletion of user data.
        
        Args:
            interaction: Discord slash command interaction
        """
        try:
            # Check if memory service is available
            if not self.memory_service.is_available():
                embed = nextcord.Embed(
                    title="❌ Service Unavailable",
                    description="Memory system is not available. No data to delete.",
                    color=0xff9900
                )
                await interaction.edit_original_response(embed=embed, view=None)
                return
            
            # Perform hard deletion
            deletion_result = await self.memory_service.hard_delete_user_data(
                str(interaction.user.id),
                str(interaction.guild.id)
            )
            
            # Create success embed
            embed = nextcord.Embed(
                title="✅ Data Deletion Complete",
                description="All your data has been permanently deleted.",
                color=0x00ff00
            )
            
            if deletion_result.get("total", 0) > 0:
                details = []
                if deletion_result.get("memories", 0) > 0:
                    details.append(f"• {deletion_result['memories']} memories")
                if deletion_result.get("summaries", 0) > 0:
                    details.append(f"• {deletion_result['summaries']} conversation summaries")
                if deletion_result.get("messages", 0) > 0:
                    details.append(f"• {deletion_result['messages']} message records")
                
                if details:
                    embed.add_field(
                        name="Deleted Items",
                        value="\n".join(details),
                        inline=False
                    )
            else:
                embed.add_field(
                    name="Result",
                    value="No stored data found to delete.",
                    inline=False
                )
            
            embed.set_footer(text="You can continue using the bot normally. New memories will be created from future conversations.")
            
            await interaction.edit_original_response(embed=embed, view=None)
            
        except Exception as e:
            logger.error(f"Hard deletion failed: {e}")
            
            embed = nextcord.Embed(
                title="❌ Deletion Failed",
                description="An error occurred while deleting your data. Please try again later or contact an administrator.",
                color=0xff0000
            )
            
            await interaction.edit_original_response(embed=embed, view=None)
    
    def _create_memory_list_embeds(
        self, 
        memories: List[MemoryHit], 
        user: nextcord.Member, 
        requested_count: int
    ) -> List[nextcord.Embed]:
        """
        Create paginated embeds for memory list display.
        
        Args:
            memories: List of memory hits to display
            user: User whose memories are being displayed
            requested_count: Number of memories requested
            
        Returns:
            List[nextcord.Embed]: List of embeds for pagination
        """
        embeds = []
        memories_per_page = 5
        total_pages = (len(memories) + memories_per_page - 1) // memories_per_page
        
        for page in range(total_pages):
            start_idx = page * memories_per_page
            end_idx = min(start_idx + memories_per_page, len(memories))
            page_memories = memories[start_idx:end_idx]
            
            embed = nextcord.Embed(
                title=f"💭 {user.display_name}'s Memories",
                description=f"Showing {len(memories)} most recent memories",
                color=0x00ff00
            )
            
            for i, memory in enumerate(page_memories, start_idx + 1):
                # Truncate long memories
                text = memory.text
                if len(text) > 200:
                    text = text[:197] + "..."
                
                # Format memory field
                field_name = f"{i}. {memory.kind.title()} Memory"
                field_value = (
                    f"**Text:** {text}\n"
                    f"**Importance:** {'⭐' * memory.importance}\n"
                    f"**Similarity:** {memory.similarity:.3f}\n"
                    f"**ID:** `{memory.id}`\n"
                    f"**Created:** {memory.created_at}"
                )
                
                embed.add_field(
                    name=field_name,
                    value=field_value,
                    inline=False
                )
            
            # Add page footer
            if total_pages > 1:
                embed.set_footer(text=f"Page {page + 1} of {total_pages}")
            
            embeds.append(embed)
        
        return embeds
    
    def _create_search_results_embed(
        self, 
        memories: List[MemoryHit], 
        query: str
    ) -> nextcord.Embed:
        """
        Create embed for search results display.
        
        Args:
            memories: List of memory hits from search
            query: Original search query
            
        Returns:
            nextcord.Embed: Formatted search results embed
        """
        embed = nextcord.Embed(
            title=f"🔍 Search Results for: `{query}`",
            description=f"Found {len(memories)} relevant memories",
            color=0x0099ff
        )
        
        for i, memory in enumerate(memories[:10], 1):  # Limit to top 10
            # Truncate long memories
            text = memory.text
            if len(text) > 150:
                text = text[:147] + "..."
            
            # Calculate relevance percentage
            relevance = int(memory.similarity * 100)
            
            field_name = f"{i}. {memory.kind.title()} ({relevance}% match)"
            field_value = (
                f"**Text:** {text}\n"
                f"**Importance:** {'⭐' * memory.importance}\n"
                f"**ID:** `{memory.id}`"
            )
            
            embed.add_field(
                name=field_name,
                value=field_value,
                inline=False
            )
        
        embed.set_footer(text="Use /mem forget <id> to delete a specific memory")
        
        return embed
    
    def _is_admin(self, user: nextcord.Member) -> bool:
        """
        Check if user has admin permissions.
        
        Args:
            user: Discord member to check
            
        Returns:
            bool: True if user has admin permissions
        """
        return user.guild_permissions.administrator
    
    def _is_valid_uuid(self, uuid_string: str) -> bool:
        """
        Validate UUID format.
        
        Args:
            uuid_string: String to validate as UUID
            
        Returns:
            bool: True if valid UUID format
        """
        import re
        uuid_pattern = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
            re.IGNORECASE
        )
        return bool(uuid_pattern.match(uuid_string))


class MemoryPaginationView(nextcord.ui.View):
    """View for paginating through memory list embeds."""
    
    def __init__(self, embeds: List[nextcord.Embed]):
        """
        Initialize pagination view.
        
        Args:
            embeds: List of embeds to paginate through
        """
        super().__init__(timeout=300)  # 5 minute timeout
        self.embeds = embeds
        self.current_page = 0
        
        # Disable buttons if only one page
        if len(embeds) <= 1:
            self.previous_button.disabled = True
            self.next_button.disabled = True
    
    @nextcord.ui.button(label="◀️ Previous", style=nextcord.ButtonStyle.secondary)
    async def previous_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        """Handle previous page button."""
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    
    @nextcord.ui.button(label="Next ▶️", style=nextcord.ButtonStyle.secondary)
    async def next_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        """Handle next page button."""
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    
    async def on_timeout(self):
        """Handle view timeout."""
        # Disable all buttons when timeout occurs
        for item in self.children:
            item.disabled = True


class ForgetMeConfirmationView(nextcord.ui.View):
    """View for confirming permanent data deletion."""
    
    def __init__(self):
        """Initialize confirmation view."""
        super().__init__(timeout=60)  # 1 minute timeout
        self.confirmed = False
        self.cancelled = False
    
    @nextcord.ui.button(label="❌ Cancel", style=nextcord.ButtonStyle.secondary)
    async def cancel_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        """Handle cancel button."""
        self.cancelled = True
        self.stop()
    
    @nextcord.ui.button(label="⚠️ Confirm Deletion", style=nextcord.ButtonStyle.danger)
    async def confirm_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        """Handle confirm deletion button."""
        self.confirmed = True
        
        # Show processing message
        embed = nextcord.Embed(
            title="🔄 Processing Deletion...",
            description="Please wait while your data is being deleted.",
            color=0xff9900
        )
        await interaction.response.edit_message(embed=embed, view=None)
        
        self.stop()
    
    async def on_timeout(self):
        """Handle view timeout."""
        embed = nextcord.Embed(
            title="⏰ Request Timed Out",
            description="Deletion request cancelled due to timeout. Your data is safe.",
            color=0xff9900
        )
        
        # Try to edit the message if possible
        try:
            if hasattr(self, 'message') and self.message:
                await self.message.edit(embed=embed, view=None)
        except Exception:
            pass  # Message might be deleted or inaccessible